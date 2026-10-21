"""Behavioral coverage for automatic, bounded refresh recovery."""
from datetime import datetime, timedelta
from unittest.mock import AsyncMock
import httpx
import pytest
from sqlalchemy import select
from app.models import MediaRequest, MediaType, RequestState, Episode, EpisodeState, LibraryRefreshJob
from app.services import library_refresh as recovery
from app.services import jellyfin_verifier as verifier
from app.clients.jellyfin import JellyfinClient
from app.clients.shoko import ShokoHttpClient

T = datetime(2026, 10, 20, 12)

@pytest.fixture
def services(monkeypatch):
    monkeypatch.setattr(recovery.settings, 'ENABLE_SHOKO', True)
    monkeypatch.setattr(recovery.settings, 'JELLYFIN_API_KEY', 'synthetic')
    monkeypatch.setattr(recovery.settings, 'SHOKO_API_KEY', 'synthetic')
    monkeypatch.setattr(verifier, 'verify_request', AsyncMock(return_value=False))
    monkeypatch.setattr(recovery.jellyfin_client, 'clear_shoko_discovery_cache', AsyncMock(return_value=True))
    monkeypatch.setattr(recovery.jellyfin_client, 'library_scan_state', AsyncMock(return_value='Idle'))
    monkeypatch.setattr(recovery.jellyfin_client, 'trigger_library_scan', AsyncMock(return_value=True))
    return recovery.jellyfin_client

async def series(db, count=2):
    r=MediaRequest(title='Synthetic', media_type=MediaType.TV, state=RequestState.ANIME_MATCHING,
                   is_anime=True, season=1, total_episodes=count, updated_at=T-timedelta(hours=1))
    r.episodes=[Episode(season_number=1,episode_number=i+1,state=EpisodeState.ANIME_MATCHING,
                        final_path=f'/data/anime/shows/Synthetic/Season 1/E{i+1}.mkv') for i in range(count)]
    db.add(r); await db.commit()
    return r

async def queue_all(db,r):
    for ep in r.episodes: await recovery.queue_refresh(db,r.id,100+ep.id,ep.id,now=T)
    await db.commit()

@pytest.mark.asyncio
async def test_season_burst_debounced_deduplicated_one_scan(db_session,services):
    r=await series(db_session,12)
    await queue_all(db_session,r); await queue_all(db_session,r)
    await recovery.process_refresh_queue(db_session,now=T)
    services.trigger_library_scan.assert_not_awaited()
    await recovery.process_refresh_queue(db_session,now=T+timedelta(seconds=31))
    services.trigger_library_scan.assert_awaited_once()
    services.clear_shoko_discovery_cache.assert_awaited_once()
    jobs=list((await db_session.scalars(select(LibraryRefreshJob))).all())
    assert len(jobs)==12 and all(j.attempts==1 for j in jobs)
    assert all(ep.state==EpisodeState.ANIME_MATCHING for ep in r.episodes)
    await recovery.process_refresh_queue(db_session,now=T+timedelta(seconds=40))
    assert services.trigger_library_scan.await_count==1

@pytest.mark.asyncio
@pytest.mark.parametrize('state',['Running','Cancelling'])
async def test_active_scan_waits_without_spending_attempts(db_session,services,state):
    r=await series(db_session); await queue_all(db_session,r)
    services.library_scan_state.return_value=state
    await recovery.process_refresh_queue(db_session,now=T+timedelta(seconds=31))
    services.trigger_library_scan.assert_not_awaited()
    job=await db_session.scalar(select(LibraryRefreshJob))
    assert job.attempts==0 and job.next_attempt_at>T+timedelta(seconds=31)

@pytest.mark.asyncio
@pytest.mark.parametrize('state',['Idle',None])
async def test_failures_bounded_and_duplicate_events_do_not_reset(db_session,services,state):
    r=await series(db_session,1); await queue_all(db_session,r)
    services.library_scan_state.return_value=state
    services.trigger_library_scan.return_value=False
    for i in range(6):
        await recovery.process_refresh_queue(db_session,now=T+timedelta(hours=i+1))
        await queue_all(db_session,r)
    job=await db_session.scalar(select(LibraryRefreshJob))
    assert job.attempts==4 and job.status=='exhausted'
    assert services.trigger_library_scan.await_count==(4 if state=='Idle' else 0)
    assert r.state==RequestState.ANIME_MATCHING

@pytest.mark.asyncio
async def test_restart_retains_attempt_budget_and_global_cooldown(db_session,services):
    r=await series(db_session,2)
    await recovery.queue_refresh(db_session,r.id,101,r.episodes[0].id,now=T)
    await db_session.commit()
    await recovery.process_refresh_queue(db_session,now=T+timedelta(seconds=31))
    # Re-open a session: no process memory is necessary to preserve the reservation.
    from sqlalchemy.ext.asyncio import AsyncSession
    async with AsyncSession(db_session.bind,expire_on_commit=False) as fresh:
        await recovery.queue_refresh(fresh,r.id,102,r.episodes[1].id,now=T+timedelta(seconds=35))
        await fresh.commit()
        await recovery.process_refresh_queue(fresh,now=T+timedelta(seconds=70))
        assert services.trigger_library_scan.await_count==1
        await recovery.process_refresh_queue(fresh,now=T+timedelta(seconds=160))
        assert services.trigger_library_scan.await_count==2
        jobs=list((await fresh.scalars(select(LibraryRefreshJob).order_by(LibraryRefreshJob.id))).all())
        assert sorted(j.attempts for j in jobs)==[1,2]

@pytest.mark.asyncio
async def test_partial_availability_finishes_only_ready_episode(db_session,services):
    r=await series(db_session); await queue_all(db_session,r)
    r.episodes[0].state=EpisodeState.AVAILABLE; await db_session.commit()
    await recovery.process_refresh_queue(db_session,now=T+timedelta(seconds=31))
    jobs=list((await db_session.scalars(select(LibraryRefreshJob).order_by(LibraryRefreshJob.episode_id))).all())
    assert [j.status for j in jobs]==['done','pending']
    assert r.state==RequestState.ANIME_MATCHING
    r.episodes[1].state=EpisodeState.AVAILABLE; r.state=RequestState.AVAILABLE
    await db_session.commit()
    await recovery.process_refresh_queue(db_session,now=T+timedelta(hours=1))
    assert services.trigger_library_scan.await_count==1
    assert jobs[1].status=='done'

@pytest.mark.asyncio
async def test_missed_event_recovery_requires_confirmed_path(db_session,services,monkeypatch):
    r=await series(db_session)
    lookup=AsyncMock(side_effect=[None,202]);monkeypatch.setattr(recovery.shoko_http_client,'confirmed_file_for_path',lookup)
    await recovery.recover_matched_files(r,db_session);await db_session.commit()
    jobs=list((await db_session.scalars(select(LibraryRefreshJob))).all())
    assert len(jobs)==1 and jobs[0].episode_id==r.episodes[1].id
    assert r.state==RequestState.ANIME_MATCHING
    assert r.episodes[0].state==EpisodeState.ANIME_MATCHING

@pytest.mark.asyncio
async def test_shoko_path_lookup_rejects_ambiguity_and_unmatched_files():
    c=ShokoHttpClient(api_key='synthetic')
    await c._client.aclose()
    file={'ID':9,'Locations':[{'RelativePath':'Synthetic/Season 1/E1.mkv','IsAccessible':True}],
          'SeriesIDs':[{'EpisodeIDs':[{'ID':42}]}]}
    async def run(data):
        c._client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=data)))
        try: return await c.confirmed_file_for_path('/data/anime/shows/Synthetic/Season 1/E1.mkv')
        finally: await c._client.aclose()
    assert await run([file])==9
    assert await run([file,file]) is None
    assert await run([{**file,'SeriesIDs':[]}]) is None
    assert await run([{**file,'Locations':[{'RelativePath':'Other/Season 1/E1.mkv','IsAccessible':True}]}]) is None

@pytest.mark.asyncio
@pytest.mark.parametrize('payload,expected',[([{'Key':'RefreshLibrary','State':'Idle'}],'Idle'),
    ([{'Key':'RefreshLibrary','State':'Running'}],'Running'),([],None),([{'Key':'RefreshLibrary','State':'Unknown'}],None),({},None)])
async def test_scan_state_validation(payload,expected):
    c=JellyfinClient();c._client=httpx.AsyncClient(base_url='http://synthetic',transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload)))
    try: assert await c.library_scan_state()==expected
    finally: await c.close()

@pytest.mark.asyncio
async def test_series_directory_does_not_mark_missing_episodes_ready(db_session,monkeypatch):
    r=await series(db_session,2)
    monkeypatch.setattr(verifier.jellyfin_client,'get_series_episodes',AsyncMock(return_value=[
        {'Id':'ep1','ParentIndexNumber':1,'IndexNumber':1,'Path':'/media/E1.mkv'},
        {'Id':'ep2','ParentIndexNumber':1,'IndexNumber':2}, # metadata only
    ]))
    monkeypatch.setattr(verifier.broadcaster,'broadcast_update',AsyncMock())
    assert not await verifier._mark_tv_available(r,{'Id':'series'},db_session,'test')
    assert r.episodes[0].state==EpisodeState.AVAILABLE
    assert r.episodes[1].state==EpisodeState.ANIME_MATCHING
    assert r.state==RequestState.ANIME_MATCHING


@pytest.mark.asyncio
async def test_missed_event_to_available_without_manual_scan(db_session,monkeypatch):
    """Exercise the actual fallback, queue and verifier with service boundaries mocked."""
    monkeypatch.setattr(recovery.settings,'ENABLE_SHOKO',True)
    monkeypatch.setattr(recovery.settings,'SHOKO_API_KEY','synthetic')
    monkeypatch.setattr(recovery.settings,'JELLYFIN_API_KEY','synthetic')
    r=await series(db_session,2)
    r.tvdb_id=123
    r.updated_at=datetime.utcnow()-timedelta(hours=1)
    await db_session.commit()
    scan=AsyncMock(return_value=True)
    monkeypatch.setattr(recovery.jellyfin_client,'trigger_library_scan',scan)
    monkeypatch.setattr(recovery.jellyfin_client,'library_scan_state',AsyncMock(return_value='Idle'))
    monkeypatch.setattr(recovery.jellyfin_client,'clear_shoko_discovery_cache',AsyncMock(return_value=True))
    async def find(*args,**kwargs):
        return {'Id':'series','Path':'/media/Synthetic','Type':'Series'} if scan.await_count else None
    monkeypatch.setattr(verifier.jellyfin_client,'find_item_by_tvdb',find)
    monkeypatch.setattr(verifier.jellyfin_client,'search_by_title',find)
    monkeypatch.setattr(verifier.jellyfin_client,'get_series_episodes',AsyncMock(return_value=[
        {'Id':f'ep-{i}','ParentIndexNumber':1,'IndexNumber':i,'Path':f'/media/E{i}.mkv'} for i in (1,2)
    ]))
    monkeypatch.setattr(verifier.broadcaster,'broadcast_update',AsyncMock())
    async def confirmed(path):
        return 201 if path.endswith('E1.mkv') else 202
    async def imported_files(ids):
        return [{'Id':f'ep-{i}', 'SeriesId':'series', 'Path':f'/media/E{i}.mkv',
                 'ProviderIds':{'Shoko File':str(200+i)}} for i in (1,2)] if scan.await_count else []
    monkeypatch.setattr(recovery.shoko_http_client,'confirmed_file_for_path',confirmed)
    monkeypatch.setattr(verifier.jellyfin_client,'find_episodes_by_shoko_files',imported_files)
    assert await verifier.check_stuck_requests_fallback(db_session)==[]
    assert r.state==RequestState.ANIME_MATCHING
    scan.assert_not_awaited()
    jobs=list((await db_session.scalars(select(LibraryRefreshJob))).all())
    due=max(j.next_attempt_at for j in jobs)+timedelta(seconds=1)
    await recovery.process_refresh_queue(db_session,now=due)
    scan.assert_awaited_once()
    assert r.state==RequestState.ANIME_MATCHING
    await recovery.process_refresh_queue(db_session,now=due+timedelta(minutes=3))
    assert r.state==RequestState.AVAILABLE
    assert all(e.state==EpisodeState.AVAILABLE for e in r.episodes)
    assert all(j.status=='done' for j in jobs)
    scan.assert_awaited_once()

@pytest.mark.asyncio
async def test_known_missing_episode_rows_cannot_complete_season(db_session,monkeypatch):
    r=await series(db_session,1);r.total_episodes=12
    monkeypatch.setattr(verifier.jellyfin_client,'get_series_episodes',AsyncMock(return_value=[
        {'Id':'ep1','ParentIndexNumber':1,'IndexNumber':1,'Path':'/media/E1.mkv'}]))
    monkeypatch.setattr(verifier.broadcaster,'broadcast_update',AsyncMock())
    assert not await verifier._mark_tv_available(r,{'Id':'series'},db_session,'test')
    assert r.state==RequestState.ANIME_MATCHING

@pytest.mark.asyncio
async def test_movie_confirmed_event_is_persisted_and_detected_event_is_not(db_session,monkeypatch):
    from app.plugins.shoko import _handle_movie_matched
    from app.clients.shoko import FileEvent
    monkeypatch.setattr(verifier.broadcaster,'broadcast_update',AsyncMock())
    import app.plugins.shoko as plugin
    monkeypatch.setattr(plugin.asyncio,'create_task',lambda coroutine:coroutine.close())
    row=MediaRequest(title='Synthetic movie',media_type=MediaType.MOVIE,is_anime=True,state=RequestState.IMPORTING)
    db_session.add(row);await db_session.commit()
    event=FileEvent(file_id=12,relative_path='anime/movies/Synthetic/movie.mkv',has_cross_references=False,managed_folder_id=1,event_type='FileMatched')
    await _handle_movie_matched(row,event,db_session)
    assert await db_session.scalar(select(LibraryRefreshJob)) is None
    event.has_cross_references=True
    await _handle_movie_matched(row,event,db_session)
    job=await db_session.scalar(select(LibraryRefreshJob))
    assert job.file_id==12 and job.status=='pending'

@pytest.mark.asyncio
@pytest.mark.parametrize('state,expected,posts', [('Idle',True,1),('Running',False,0),('Cancelling',False,0),('Unknown',False,0)])
async def test_shokofin_task_discovered_by_key(state,expected,posts):
    seen=[]
    def handler(req):
        if req.method=='GET':
            return httpx.Response(200,json=[{'Key':'RefreshLibrary','Id':'scan','State':'Idle'}, {'Key':'ShokoClearPluginCache','Id':'installed-task','State':state,'LastExecutionResult':{'EndTimeUtc':'new' if seen else 'old','Status':'Completed'}}])
        seen.append(req.url.path)
        return httpx.Response(204)
    client=JellyfinClient()
    client._client=httpx.AsyncClient(base_url='http://test',transport=httpx.MockTransport(handler))
    try:
        assert await client.clear_shoko_discovery_cache() is expected
        assert len(seen)==posts
        if posts:assert seen==['/ScheduledTasks/Running/installed-task']
    finally:await client.close()

@pytest.mark.asyncio
async def test_missing_shokofin_task_does_not_dispatch():
    seen=[]
    def handler(req):
        seen.append(req.method)
        return httpx.Response(200,json=[])
    client=JellyfinClient()
    client._client=httpx.AsyncClient(base_url='http://test',transport=httpx.MockTransport(handler))
    try:
        assert not await client.clear_shoko_discovery_cache()
        assert seen==['GET']
    finally:await client.close()

@pytest.mark.asyncio
async def test_metadata_failure_retains_bounded_pending_job(db_session,services):
    r=await series(db_session,1);await queue_all(db_session,r)
    services.clear_shoko_discovery_cache.return_value=False
    await recovery.process_refresh_queue(db_session,now=T+timedelta(seconds=31))
    job=await db_session.scalar(select(LibraryRefreshJob))
    assert job.status=='pending' and job.attempts==1 and job.last_error=='cache_refresh_unavailable'
    services.trigger_library_scan.assert_not_awaited()
    assert r.state==RequestState.ANIME_MATCHING

@pytest.mark.asyncio
@pytest.mark.parametrize('busy_key',['RefreshLibrary','ShokoAutoRefreshMetadata'])
async def test_cache_clear_refuses_active_scans_or_metadata(busy_key):
    seen=[]
    def handler(req):
        seen.append(req.method)
        return httpx.Response(200,json=[{'Key':'RefreshLibrary','Id':'scan','State':'Running' if busy_key=='RefreshLibrary' else 'Idle'}, {'Key':'ShokoAutoRefreshMetadata','Id':'metadata','State':'Running' if busy_key=='ShokoAutoRefreshMetadata' else 'Idle'}, {'Key':'ShokoClearPluginCache','Id':'clear','State':'Idle'}])
    client=JellyfinClient();client._client=httpx.AsyncClient(base_url='http://test',transport=httpx.MockTransport(handler))
    try:
        assert not await client.clear_shoko_discovery_cache()
        assert seen==['GET']
    finally:await client.close()

@pytest.mark.asyncio
async def test_cache_clear_precedes_scan(db_session,services):
    r=await series(db_session,1);await queue_all(db_session,r)
    order=[]
    async def clear():order.append('clear');return True
    async def scan():order.append('scan');return True
    services.clear_shoko_discovery_cache.side_effect=clear
    services.trigger_library_scan.side_effect=scan
    await recovery.process_refresh_queue(db_session,now=T+timedelta(seconds=31))
    assert order==['clear','scan']
