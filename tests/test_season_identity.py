from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select
from fastapi import FastAPI
from httpx import AsyncClient,ASGITransport
from app.models import MediaRequest,MediaType,RequestState,Episode,EpisodeState
from app.database import get_db
from app.routers.pages import router
from app.services.auth import get_current_user
from app.core.correlator import correlator

async def pair(db):
 rows=[]
 for season in [1,2]:
  r=MediaRequest(title='Two seasons',media_type=MediaType.TV,state=RequestState.APPROVED,
    tmdb_id=123,tvdb_id=456,season=season,requested_seasons=str(season),jellyseerr_id=100+season,total_episodes=2)
  r.episodes=[];db.add(r);rows.append(r)
 await db.commit();return rows

@pytest.mark.asyncio
async def test_separate_jellyseerr_request_does_not_reuse_show(db_session,monkeypatch):
 from app.plugins.jellyseerr import JellyseerrPlugin,jellyseerr_client
 monkeypatch.setattr(jellyseerr_client,'get_tv_season_episode_count',AsyncMock(return_value=2))
 p=JellyseerrPlugin()
 rows=[]
 for season in [2,1]:
  payload={'notification_type':'MEDIA_AUTO_APPROVED','subject':'Synthetic','media':{'media_type':'tv','tmdbId':'123','tvdbId':'456'},'request':{'request_id':100+season},'extra':[{'name':'Requested Seasons','value':str(season)}]}
  rows.append(await p.handle_webhook(payload,db_session));await db_session.commit()
  repeated=await p.handle_webhook(payload,db_session)
  assert repeated.id==rows[-1].id
 assert rows[0].id!=rows[1].id and [r.season for r in rows]==[2,1]

@pytest.mark.asyncio
async def test_correlation_keeps_sibling_seasons_distinct(db_session):
 a,b=await pair(db_session)
 assert await correlator.find_by_any(db_session,tvdb_id=456,season=1) is a
 assert await correlator.find_by_any(db_session,tmdb_id=123,season=2) is b
 assert await correlator.find_by_any(db_session,tvdb_id=456) is None

@pytest.mark.asyncio
async def test_sonarr_grab_targets_requested_season(db_session,monkeypatch):
 from app.plugins.sonarr import SonarrPlugin
 a,b=await pair(db_session);p=SonarrPlugin();mock=AsyncMock(return_value=a)
 monkeypatch.setattr(p,'_handle_grab',mock)
 await p.handle_webhook({'eventType':'Grab','series':{'tvdbId':456},'episodes':[{'seasonNumber':1,'episodeNumber':1}]},db_session)
 assert mock.await_args.args[0] is a
 assert b.state==RequestState.APPROVED

@pytest.mark.asyncio
async def test_episode_webhook_verifies_instead_of_completing_whole_season(db_session,monkeypatch):
 from app.plugins.jellyfin import JellyfinPlugin
 from app.services import jellyfin_verifier
 a,b=await pair(db_session);a.state=RequestState.ANIME_MATCHING
 a.episodes=[Episode(season_number=1,episode_number=n,state=EpisodeState.ANIME_MATCHING) for n in [1,2]]
 await db_session.commit()
 verify=AsyncMock(return_value=False);monkeypatch.setattr(jellyfin_verifier,'verify_request',verify)
 await JellyfinPlugin().handle_webhook({'NotificationType':'ItemAdded','ItemType':'Episode','Provider_tvdb':'456','SeasonNumber':1,'EpisodeNumber':1,'ItemId':'one-episode'},db_session)
 assert verify.await_args.args[0] is a
 assert all(e.state==EpisodeState.ANIME_MATCHING for e in a.episodes)
 assert b.state==RequestState.APPROVED

@pytest.mark.asyncio
async def test_grouped_card_and_related_season_details(db_session):
 a,b=await pair(db_session);a.state=RequestState.DOWNLOADING;a.download_progress=.25
 await db_session.commit()
 app=FastAPI();app.include_router(router)
 async def db():yield db_session
 app.dependency_overrides[get_db]=db;app.dependency_overrides[get_current_user]=lambda:None
 async with AsyncClient(transport=ASGITransport(app=app),base_url='http://test') as c:
  page=(await c.get('/')).text
  assert page.count('class="reqcard"')==1 and 'S01' in page and 'S02' in page and 'Requested' in page
  detail=(await c.get(f'/request/{a.id}')).text
  assert 'data-related-season="1"' in detail and 'data-related-season="2"' in detail
  assert f'href="/request/{b.id}"' in detail and 'Waiting for a download.' in detail
  a.state=RequestState.AVAILABLE;await db_session.commit()
  page=(await c.get('/')).text
  assert f'id="request-{b.id}"' in page and 'S01' in page and 'S02' in page

@pytest.mark.asyncio
async def test_jellyseerr_available_verifies_requested_season(db_session, monkeypatch):
 from app.plugins.jellyseerr import JellyseerrPlugin
 from app.services import jellyfin_verifier
 a,b=await pair(db_session)
 verify=AsyncMock(return_value=False)
 monkeypatch.setattr(jellyfin_verifier,'verify_request',verify)
 await JellyseerrPlugin().handle_webhook({'notification_type':'MEDIA_AVAILABLE','media':{'media_type':'tv','tvdbId':'456'},'request':{'request_id':'102'}},db_session)
 assert verify.await_args.args[0] is b
 assert a.state==b.state==RequestState.APPROVED
