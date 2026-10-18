"""Never infer an import from elapsed time, and clear completed TV transfer data."""
from datetime import datetime,timedelta
from unittest.mock import AsyncMock
import pytest
from app.models import MediaRequest,MediaType,RequestState,Episode,EpisodeState
from app.services import jellyfin_verifier as verifier
from app.plugins.qbittorrent import QBittorrentPlugin

@pytest.mark.asyncio
@pytest.mark.parametrize('state',[RequestState.DOWNLOADED,RequestState.IMPORTING,RequestState.ANIME_MATCHING])
@pytest.mark.parametrize('anime',[True,False])
async def test_unverified_fallback_preserves_observed_stage(db_session,monkeypatch,state,anime):
    row=MediaRequest(title='Synthetic',media_type=MediaType.MOVIE,state=state,is_anime=anime,
                     updated_at=datetime.utcnow()-timedelta(hours=1))
    db_session.add(row);await db_session.commit()
    monkeypatch.setattr(verifier,'verify_request',AsyncMock(return_value=False))
    monkeypatch.setattr(verifier,'_check_and_rebuild_vfs_if_needed',AsyncMock())
    monkeypatch.setattr(verifier.settings,'ENABLE_SHOKO',False)
    assert await verifier.check_stuck_requests_fallback(db_session)==[]
    assert row.state==state
    verifier.verify_request.assert_awaited_once()

@pytest.mark.asyncio
async def test_fallback_still_recovers_confirmed_availability(db_session,monkeypatch):
    row=MediaRequest(title='Synthetic',media_type=MediaType.MOVIE,state=RequestState.DOWNLOADED,
                     updated_at=datetime.utcnow()-timedelta(hours=1))
    db_session.add(row);await db_session.commit()
    async def verified(request,db):
        request.state=RequestState.AVAILABLE
        return True
    monkeypatch.setattr(verifier,'verify_request',verified)
    monkeypatch.setattr(verifier,'_check_and_rebuild_vfs_if_needed',AsyncMock())
    monkeypatch.setattr(verifier.settings,'ENABLE_SHOKO',False)
    broadcast=AsyncMock();monkeypatch.setattr(verifier.broadcaster,'broadcast_update',broadcast)
    assert await verifier.check_stuck_requests_fallback(db_session)==[row]
    await db_session.refresh(row)
    assert row.state==RequestState.AVAILABLE
    broadcast.assert_awaited_once_with(row)

@pytest.mark.asyncio
async def test_completed_tv_clears_speed_eta_even_without_transition(db_session):
    row=MediaRequest(title='Synthetic',media_type=MediaType.TV,state=RequestState.DOWNLOADED,
                     download_speed='7 MB/s',download_eta='23h 59m',season=1,total_episodes=2)
    row.episodes=[Episode(season_number=1,episode_number=i,state=EpisodeState.DOWNLOADED) for i in [1,2]]
    db_session.add(row);await db_session.commit()
    await QBittorrentPlugin()._recalculate_request_state(row,db_session)
    assert row.download_progress==1
    assert row.download_speed is None and row.download_eta is None
