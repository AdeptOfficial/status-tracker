from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from app.database import engine, Base, async_session
from app.models import MediaRequest, MediaType, RequestState, TimelineEvent, Episode, EpisodeState
from app.routers.pages import router as pages
from app.routers.sse import router as sse
from app.core.broadcaster import broadcaster

@asynccontextmanager
async def lifespan(app):
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    async with async_session() as db:
        db.add(MediaRequest(id=1,title='Synthetic browser test',requested_by='synthetic-reviewer',media_type=MediaType.MOVIE,state=RequestState.DOWNLOADING,download_progress=.1,download_speed='1 MB/s',download_eta='10m'))
        tv=MediaRequest(id=2,title='Synthetic Series With a Long Descriptive Season Title',media_type=MediaType.TV,state=RequestState.DOWNLOADING,season=2,total_episodes=5,tvdb_id=123456,poster_url='/static/emblem.png',quality='HDTV-1080p',requested_by='synthetic-reviewer')
        tv.episodes=[Episode(season_number=2,episode_number=1,state=EpisodeState.AVAILABLE),
                     Episode(season_number=2,episode_number=2,state=EpisodeState.ANIME_MATCHING),
                     Episode(season_number=2,episode_number=3,state=EpisodeState.DOWNLOADING,download_progress=.37),
                     Episode(season_number=2,episode_number=4,state=EpisodeState.DOWNLOADING),
                     Episode(season_number=1,episode_number=1,state=EpisodeState.AVAILABLE)]
        tv.episodes[2].episode_title='A Long Episode Title That Should Truncate Inside Its Row'
        db.add(tv)
        db.add(MediaRequest(id=4,title=tv.title,media_type=MediaType.TV,state=RequestState.APPROVED,season=3,total_episodes=5,tvdb_id=123456,requested_seasons='3'))
        db.add(TimelineEvent(request_id=2,service='sonarr',event_type='Import',state=RequestState.IMPORTING,details='Imported: Synthetic.Series.With.A.Very.Long.Release.Name.S02E03.1080p.HEVC.AAC.ReleaseGroup.mkv'))
        db.add(MediaRequest(id=3,title='Synthetic import',media_type=MediaType.MOVIE,state=RequestState.AVAILABLE,jellyfin_id='fixture-library',requested_by='Library Sync'))
        await db.commit()
    yield

app=FastAPI(lifespan=lifespan)
app.mount('/static',StaticFiles(directory='/app/app/static'),name='static')
app.include_router(pages)
app.include_router(sse)
@app.post('/test/update/{percent}')
async def update(percent:int):
    async with async_session() as db:
        r=(await db.execute(select(MediaRequest).options(selectinload(MediaRequest.episodes),selectinload(MediaRequest.timeline_events)).where(MediaRequest.id==1))).scalar_one()
        r.download_progress=percent/100
        if percent==100: r.state=RequestState.AVAILABLE
        r.download_speed='5 MB/s'
        r.download_eta='2m'
        db.add(TimelineEvent(request_id=1,service='test',event_type='progress',state=RequestState.DOWNLOADING,details=f'Synthetic progress {percent}'))
        await db.commit()
        await broadcaster.broadcast_update(r,'progress_update')
    return {'ok':True}

@app.post('/test/episode-update')
async def episode_update():
    async with async_session() as db:
        r=(await db.execute(select(MediaRequest).options(selectinload(MediaRequest.episodes),selectinload(MediaRequest.timeline_events)).where(MediaRequest.id==2))).scalar_one()
        for ep in r.episodes:
            if ep.season_number==2 and ep.episode_number==3:
                ep.download_progress=1
        await db.commit()
        await broadcaster.broadcast_update(r,'progress_update')
    return {'ok':True}

# Only this isolated fixture bypasses authentication and mocks media clients.
from unittest.mock import AsyncMock
from app.routers.api import router as api
from app.services.auth import get_current_user, AuthenticatedUser
from app.services import library_sync
app.include_router(api)
app.dependency_overrides[get_current_user] = lambda: AuthenticatedUser(user_id='fixture', username='fixture-admin', is_admin=True)
library_sync.jellyfin_client.trigger_library_scan = AsyncMock(return_value=True)
library_sync.jellyfin_client.get_all_items = AsyncMock(return_value=[{
    'Id': 'fixture-library', 'Type': 'Movie', 'Name': 'Synthetic import',
    'ProductionYear': 2020, 'ProviderIds': {'Tmdb': '901'},
}])
library_sync.radarr_client.get_all_movies = AsyncMock(return_value=[])
library_sync.sonarr_client.get_all_series = AsyncMock(return_value=[])
