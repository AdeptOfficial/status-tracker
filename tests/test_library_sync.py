from unittest.mock import AsyncMock
import pytest
import httpx
from fastapi import FastAPI
from sqlalchemy import select, func
from app.models import MediaRequest, MediaType, RequestState
from app.services.library_sync import LibrarySyncService
from app.services import library_sync as module


def item(kind='Movie', jid='jf-one', tmdb='101', tvdb=None, **extra):
    return dict(Id=jid,Type=kind,Name='Synthetic library item',ProviderIds={'Tmdb':tmdb,'Tvdb':tvdb},ProductionYear=2020,ImageTags={'Primary':'image'},**extra)


@pytest.fixture
def sources(monkeypatch):
    jf=AsyncMock(return_value=[])
    monkeypatch.setattr(module.jellyfin_client,'get_all_items',jf)
    monkeypatch.setattr(module.jellyfin_client,'trigger_library_scan',AsyncMock(return_value=True))
    monkeypatch.setattr(module.radarr_client,'get_all_movies',AsyncMock(return_value=[{'tmdbId':101,'id':9}]))
    monkeypatch.setattr(module.sonarr_client,'get_all_series',AsyncMock(return_value=[{'tvdbId':202,'id':8}]))
    return jf


async def add(db, **fields):
    defaults=dict(title='Original title',media_type=MediaType.MOVIE,state=RequestState.DOWNLOADING)
    defaults.update(fields)
    row=MediaRequest(**defaults);db.add(row);await db.commit();return row


@pytest.mark.asyncio
@pytest.mark.parametrize('kind,media_type,fields', [('Movie',MediaType.MOVIE,{'tmdb_id':101}),('Series',MediaType.TV,{'tvdb_id':202}),('Movie',MediaType.MOVIE,{'jellyfin_id':'jf-one'}),('Series',MediaType.TV,{'jellyfin_id':'jf-one'})])
async def test_repairs_missing_ids_preserves_state_and_is_idempotent(db_session,sources,kind,media_type,fields):
    row=await add(db_session,media_type=media_type,**fields)
    sources.return_value=[item(kind=kind,tvdb='202')]
    service=LibrarySyncService(db_session)
    result=await service.sync_available_content()
    assert result.added==0 and result.updated==1 and result.errors==0
    assert row.jellyfin_id=='jf-one' and row.tmdb_id==101 and row.tvdb_id==202
    assert row.year==2020 and row.poster_url.endswith('/Items/jf-one/Images/Primary')
    assert (row.radarr_id if media_type==MediaType.MOVIE else row.sonarr_id)==(9 if media_type==MediaType.MOVIE else 8)
    assert row.state==RequestState.DOWNLOADING and row.title=='Original title'
    await db_session.refresh(row)
    assert row.tmdb_id==101
    result=await service.sync_available_content()
    assert result.added==0 and result.updated==0


@pytest.mark.asyncio
async def test_existing_values_never_overwritten(db_session,sources):
    row=await add(db_session,jellyfin_id='jf-one',tmdb_id=101,tvdb_id=202,year=1999,poster_url='saved',radarr_id=55)
    sources.return_value=[item(tvdb='202')]
    result=await LibrarySyncService(db_session).sync_available_content()
    assert result.updated==0
    assert (row.year,row.poster_url,row.radarr_id)==(1999,'saved',55)


@pytest.mark.asyncio
@pytest.mark.parametrize('items',[[item(jid='a'),item(jid='b')],[item(tvdb='999')]])
async def test_ambiguous_and_conflicting_matches_are_not_repaired(db_session,sources,items):
    row=await add(db_session,tmdb_id=101,tvdb_id=202)
    sources.return_value=items
    await LibrarySyncService(db_session).sync_available_content()
    assert row.jellyfin_id is None and row.poster_url is None and row.year is None


@pytest.mark.asyncio
async def test_jellyfin_id_match_wins_and_no_image_is_not_invented(db_session,sources):
    row=await add(db_session,jellyfin_id='chosen',tmdb_id=101)
    chosen=item(jid='chosen');chosen['ImageTags']={}
    sources.return_value=[item(jid='other'),chosen]
    await LibrarySyncService(db_session).sync_available_content()
    assert row.year==2020 and row.poster_url is None


@pytest.mark.asyncio
async def test_same_number_movie_and_tv_do_not_collide(db_session,sources):
    row=await add(db_session,media_type=MediaType.TV,tmdb_id=101)
    sources.return_value=[item()]
    result=await LibrarySyncService(db_session).sync_available_content()
    assert result.added==1 and row.jellyfin_id is None
    assert await db_session.scalar(select(func.count()).select_from(MediaRequest))==2


@pytest.mark.asyncio
async def test_shoko_id_is_not_anidb_identity(db_session,sources):
    row=await add(db_session,media_type=MediaType.TV,shoko_series_id=303)
    media=item(kind='Series',tmdb=None);media['ProviderIds']={'AniDB':'303'}
    sources.return_value=[media]
    await LibrarySyncService(db_session).sync_available_content()
    assert row.jellyfin_id is None


@pytest.mark.asyncio
async def test_metadata_failure_counts_error_and_rolls_back_repairs(db_session,sources,monkeypatch):
    row=await add(db_session,tmdb_id=101);row_id=row.id
    sources.return_value=[item()]
    service=LibrarySyncService(db_session)
    async def fail(**kwargs):
        row.year=2020;await db_session.flush();raise ValueError('synthetic failure')
    monkeypatch.setattr(service,'_update_missing_metadata',fail)
    result=await service.sync_available_content()
    assert result.errors==1 and result.updated==0 and result.error_details
    await db_session.refresh(row)
    assert row.year is None


@pytest.mark.parametrize('value',[True,False,0,-1,1.5,'bad',''])
def test_invalid_provider_ids(value):
    assert LibrarySyncService._parse_int(value) is None


@pytest.mark.asyncio
@pytest.mark.parametrize('role,status',[(None,401),(False,403),(True,200)])
async def test_admin_sync_api_gate_and_updated_result(db_session,sources,role,status):
    from app.routers.api import router
    from app.database import get_db
    from app.services.auth import get_current_user,AuthenticatedUser
    await add(db_session,jellyfin_id='jf-one');sources.return_value=[item()]
    app=FastAPI();app.include_router(router)
    async def session(): yield db_session
    async def user(): return None if role is None else AuthenticatedUser('test','test',role)
    app.dependency_overrides[get_db]=session;app.dependency_overrides[get_current_user]=user
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://test') as client:
        response=await client.post('/api/admin/sync/library')
    assert response.status_code==status
    if status==200: assert response.json()['updated']==1
    else: sources.assert_not_awaited()
