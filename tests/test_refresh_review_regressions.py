from datetime import datetime,timedelta
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select
from app.models import MediaRequest,MediaType,RequestState,Episode,EpisodeState,LibraryRefreshJob
from app.services import library_refresh as recovery,jellyfin_verifier as verifier

async def make(db,season=1,episode_season=1):
 r=MediaRequest(title='Review fixture',media_type=MediaType.TV,state=RequestState.ANIME_MATCHING,is_anime=True,season=season,total_episodes=1)
 r.episodes=[Episode(season_number=episode_season,episode_number=1,state=EpisodeState.ANIME_MATCHING,final_path='/data/anime/show/new.mkv')]
 db.add(r);await db.commit();return r

@pytest.mark.asyncio
@pytest.mark.parametrize('requested_season',[0,2])
async def test_other_season_cannot_satisfy_requested_season(db_session,monkeypatch,requested_season):
 r=await make(db_session,season=requested_season,episode_season=1)
 monkeypatch.setattr(verifier.jellyfin_client,'get_series_episodes',AsyncMock(return_value=[{'Id':'old-season','ParentIndexNumber':1,'IndexNumber':1,'Path':'/media/S01E01.mkv'}]))
 assert await verifier._mark_tv_available(r,{'Id':'series'},db_session,'review') is False
 assert r.state!=RequestState.AVAILABLE

@pytest.mark.asyncio
async def test_new_file_can_recover_after_old_job_completed(db_session,monkeypatch):
 monkeypatch.setattr(recovery.settings,'ENABLE_SHOKO',True)
 monkeypatch.setattr(recovery.settings,'SHOKO_API_KEY','synthetic')
 r=await make(db_session)
 await recovery.queue_refresh(db_session,r.id,100,r.episodes[0].id)
 old=await db_session.scalar(select(LibraryRefreshJob));old.status='done';await db_session.commit()
 lookup=AsyncMock(return_value=200)
 monkeypatch.setattr(recovery.shoko_http_client,'confirmed_file_for_path',lookup)
 await recovery.recover_matched_files(r,db_session)
 new=await db_session.scalar(select(LibraryRefreshJob).where(LibraryRefreshJob.file_id==200))
 assert new is not None, 'new matched file has no recovery intent'

@pytest.mark.asyncio
@pytest.mark.parametrize('fail_first',[True,False])
async def test_one_bad_request_does_not_starve_other_requests(db_session,monkeypatch,fail_first):
 monkeypatch.setattr(recovery.settings,'ENABLE_SHOKO',True)
 monkeypatch.setattr(recovery.settings,'JELLYFIN_API_KEY','synthetic')
 a=await make(db_session);b=await make(db_session);bad_id=a.id if fail_first else b.id
 now=datetime.utcnow()
 for r in [a,b]:await recovery.queue_refresh(db_session,r.id,100+r.id,r.episodes[0].id,now=now-timedelta(minutes=1))
 await db_session.commit()
 async def verify(request,db):
  if request.id==bad_id:
   request.title='must roll back'
   await db.flush()
   raise ValueError('malformed per-request metadata')
  return False
 monkeypatch.setattr(verifier,'verify_request',verify)
 monkeypatch.setattr(recovery.jellyfin_client, 'clear_shoko_discovery_cache', AsyncMock(return_value=True))
 monkeypatch.setattr(recovery.jellyfin_client,'library_scan_state',AsyncMock(return_value='Idle'))
 scan=AsyncMock(return_value=True);monkeypatch.setattr(recovery.jellyfin_client,'trigger_library_scan',scan)
 await recovery.process_refresh_queue(db_session,now=now)
 assert scan.await_count==1,'healthy request never gets its refresh'

 jobs=list((await db_session.scalars(select(LibraryRefreshJob))).all())
 bad=next(j for j in jobs if j.request_id==bad_id)
 good=next(j for j in jobs if j.request_id!=bad_id)
 assert bad.last_error=='verification_failed' and bad.attempts==0
 assert good.attempts==1 and good.last_error is None
 await db_session.refresh(a);await db_session.refresh(b)
 assert a.title==b.title=='Review fixture'

@pytest.mark.asyncio
@pytest.mark.parametrize('status',['done','exhausted'])
async def test_same_file_recovery_does_not_reset_terminal_job(db_session,monkeypatch,status):
 monkeypatch.setattr(recovery.settings,'ENABLE_SHOKO',True)
 monkeypatch.setattr(recovery.settings,'SHOKO_API_KEY','synthetic')
 r=await make(db_session)
 await recovery.queue_refresh(db_session,r.id,100,r.episodes[0].id)
 old=await db_session.scalar(select(LibraryRefreshJob));old.status=status;old.attempts=4
 await db_session.commit()
 monkeypatch.setattr(recovery.shoko_http_client,'confirmed_file_for_path',AsyncMock(return_value=100))
 await recovery.recover_matched_files(r,db_session)
 jobs=list((await db_session.scalars(select(LibraryRefreshJob))).all())
 assert len(jobs)==1 and old.status==status and old.attempts==4
