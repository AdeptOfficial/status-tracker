from types import SimpleNamespace as Obj
from unittest.mock import AsyncMock
import httpx
import pytest
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import create_async_engine
from app.services.episode_progress import file_progress, episode_summary, episode_percent
from app.models import Episode, EpisodeState, MediaRequest, MediaType, RequestState
from app.database import run_migrations
from app.plugins.qbittorrent import QBittorrentPlugin
from app.clients.qbittorrent import QBittorrentClient, TorrentInfo


def ep(n, state='downloading', progress=None, season=2):
    return Obj(season_number=season, episode_number=n, state=Obj(value=state), download_progress=progress)


def test_season_pack_uses_file_progress_not_torrent_average():
    assert file_progress([ep(1),ep(2)], [
        {'name':'Show/Show.S02E01.mkv','progress':1},
        {'name':'Show/Show.S02E02.mkv','progress':.37},
        {'name':'Show/Show.S02E02.srt','progress':1},
    ]) == {(2,1):1.,(2,2):.37}


@pytest.mark.parametrize('files',[
    [{'name':'Show.S02E01.mkv','progress':.4},{'name':'sample.S02E01.mkv','progress':1}],
    [{'name':'Show.S02E01E02.mkv','progress':.4}],
    [{'name':'Show.S02E01-E02.mkv','progress':.4}],
    [{'name':'Show.S02E01.mkv','progress':.4,'priority':0}],
    [{'name':'Show.S02E01.mkv','progress':float('nan')}],
    [{'name':'Show.S02E01.mkv','progress':1.5}],
    [{'name':'Show.S02E01.mkv','progress':True}],
    [{'name':'Show.S01E01.mkv','progress':.4}],
    [{'name':'01.mkv','progress':.4},{'name':'02.mkv','progress':.8}],
    [],
])
def test_ambiguous_or_invalid_file_progress_is_unknown(files):
    assert file_progress([ep(1),ep(2)],files)=={}


def test_single_video_fallback_and_multiple_season_keys():
    assert file_progress([ep(1)], [{'name':'absolute-12.mkv','progress':.6}])=={(2,1):.6}
    assert file_progress([ep(1),ep(1,season=1)], [{'name':'absolute-12.mkv','progress':.6}])=={}
    assert file_progress([ep(1)], [{'name':'Show.S01E01.mkv','progress':.6}])=={}


def test_summary_scopes_season_and_separates_downloaded_ready():
    req=Obj(season=2,total_episodes=8,episodes=[ep(1,'available'),ep(2,'importing'),ep(3,'anime_matching'),ep(4,progress=1),ep(5,progress=.8),ep(6,'failed'),ep(1,'available',season=1)])
    assert episode_summary(req)=={'downloaded':4,'ready':1,'total':8}
    req.total_episodes=2
    assert episode_summary(req)['total']==6


def test_percent_unknown_zero_and_no_premature_completion():
    assert episode_percent(ep(1)) is None
    assert episode_percent(ep(1,progress=0))==0
    assert episode_percent(ep(1,progress=.9999))==99
    assert episode_percent(ep(1,progress=1))==100


@pytest.mark.asyncio
async def test_old_database_migration_is_additive_and_repeatable():
    engine=create_async_engine('sqlite+aiosqlite:///:memory:')
    try:
        async with engine.begin() as conn:
            await conn.execute(text('CREATE TABLE episodes (id INTEGER PRIMARY KEY, episode_number INTEGER)'))
            await conn.execute(text('INSERT INTO episodes VALUES(1,7)'))
            await run_migrations(conn)
            await run_migrations(conn)
            assert (await conn.execute(text('SELECT episode_number, download_progress FROM episodes'))).one()==(7,None)
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_poll_fetches_files_once_per_hash_and_persists(db_session):
    req=MediaRequest(title='Synthetic pack',media_type=MediaType.TV,state=RequestState.DOWNLOADING,season=2,total_episodes=2)
    req.episodes=[Episode(season_number=2,episode_number=n,state=EpisodeState.DOWNLOADING,qbit_hash='abc') for n in (1,2)]
    db_session.add(req);await db_session.commit()
    torrent=TorrentInfo('abc','Pack',.6,'downloading',100,60,10,4,'/synthetic')
    client=Obj(get_torrents=AsyncMock(return_value=[torrent]),get_files=AsyncMock(return_value=[{'name':'S02E01.mkv','progress':1},{'name':'S02E02.mkv','progress':.2}]))
    plugin=QBittorrentPlugin();plugin._get_client=AsyncMock(return_value=client)
    updated=await plugin.poll(db_session);await db_session.commit()
    assert updated==[req]
    client.get_files.assert_awaited_once_with('abc')
    db_session.expire_all()
    rows=(await db_session.execute(select(Episode).order_by(Episode.episode_number))).scalars().all()
    assert [e.download_progress for e in rows]==[1,.2]
    assert all(e.state==EpisodeState.DOWNLOADING for e in rows)
    client.get_files.return_value=[]
    await plugin.poll(db_session);await db_session.commit()
    assert all(e.download_progress is None for e in rows)


@pytest.mark.asyncio
@pytest.mark.parametrize('status,body',[(200,[{'name':'S02E01.mkv','progress':.4}]),(403,{}),(200,{'bad':'shape'})])
async def test_file_api_response_handling(status,body):
    client=QBittorrentClient();client._authenticated=True
    def respond(request):
        assert request.url.path=='/api/v2/torrents/files'
        assert request.url.params['hash']=='abc'
        return httpx.Response(status,json=body)
    client._client=httpx.AsyncClient(base_url='http://test',transport=httpx.MockTransport(respond))
    try:
        assert await client.get_files('abc') == (body if status==200 and isinstance(body,list) else [])
    finally: await client.close()

@pytest.mark.asyncio
async def test_regrab_clears_previous_file_progress(db_session, load_webhook):
    from app.plugins.sonarr import SonarrPlugin
    from sqlalchemy.orm import selectinload
    req=MediaRequest(title='Synthetic regrab',media_type=MediaType.TV,state=RequestState.APPROVED,tvdb_id=414057)
    db_session.add(req);await db_session.commit()
    plugin=SonarrPlugin();payload=load_webhook('sonarr-grab')
    await plugin.handle_webhook(payload,db_session);await db_session.commit()
    rows=(await db_session.execute(select(Episode).where(Episode.request_id==req.id))).scalars().all()
    assert rows
    for row in rows: row.download_progress=.8
    await db_session.commit()
    payload['downloadId']='replacement-torrent'
    await plugin.handle_webhook(payload,db_session);await db_session.commit()
    assert all(row.download_progress is None for row in rows)
