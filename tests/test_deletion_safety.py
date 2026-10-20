"""Deletion regressions use isolated DBs and fake services, never real media."""
from unittest.mock import AsyncMock
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from sqlalchemy import select
from app.models import MediaRequest, MediaType, DeletionLog, DeletionStatus, DeletionSource
from app.services import deletion_orchestrator as deletion
from app.routers.api import bulk_delete_requests
from app.schemas import BulkDeleteRequestPayload

@pytest.fixture(autouse=True)
def services(monkeypatch):
    monkeypatch.setattr(deletion.settings, "ENABLE_DELETION_SYNC", True)
    for client, methods in [
        (deletion.sonarr_client, ["delete_series"]),
        (deletion.radarr_client, ["delete_movie"]),
        (deletion.jellyfin_client, ["delete_item"]),
        (deletion.jellyseerr_client, ["delete_request", "delete_media"]),
        (deletion.shoko_http_client, ["remove_missing_files"]),
    ]:
        for method in methods:
            monkeypatch.setattr(client, method, AsyncMock(return_value=(True, "done")))
    monkeypatch.setattr(deletion.jellyseerr_client, "get_media_id_by_tmdb", AsyncMock(side_effect=[91, None]))
    monkeypatch.setattr(deletion.jellyseerr_client, "verify_request_removed", AsyncMock(return_value=True))
    monkeypatch.setattr(deletion.broadcaster, "broadcast", AsyncMock())
    monkeypatch.setattr(deletion.radarr_client, "get_movie_strict", AsyncMock(return_value={"id": 3, "tmdbId": 123, "path": "/movies/Synthetic"}))
    monkeypatch.setattr(deletion.jellyfin_client, "wait_for_item_removal", AsyncMock(return_value=True))

async def add(db, kind=MediaType.MOVIE, **kwargs):
    item = MediaRequest(title="Synthetic", media_type=kind, tmdb_id=123, **kwargs)
    db.add(item)
    await db.commit()
    return item

@pytest.mark.asyncio
@pytest.mark.parametrize("source", [DeletionSource.DASHBOARD, DeletionSource.SONARR])
async def test_tv_scope_rejected_before_mutations(db_session, source):
    first = await add(db_session, MediaType.TV, season=1, sonarr_id=5)
    sibling = await add(db_session, MediaType.TV, season=2, sonarr_id=5)
    with pytest.raises(deletion.UnsafeDeletionError, match="sibling seasons"):
        await deletion.delete_request(db_session, first.id, source=source)
    assert await db_session.get(MediaRequest, first.id)
    assert await db_session.get(MediaRequest, sibling.id)
    assert not (await db_session.execute(select(DeletionLog))).scalars().all()
    deletion.sonarr_client.delete_series.assert_not_awaited()
    deletion.jellyfin_client.delete_item.assert_not_awaited()
    deletion.jellyseerr_client.delete_media.assert_not_awaited()

@pytest.mark.asyncio
async def test_bulk_preflight_prevents_partial_movie_deletion(db_session):
    movie = await add(db_session, radarr_id=3)
    tv = await add(db_session, MediaType.TV, season=1)
    with pytest.raises(HTTPException) as error:
        await bulk_delete_requests(BulkDeleteRequestPayload(request_ids=[movie.id, tv.id]),
                                   SimpleNamespace(user_id="admin", username="admin"), db_session)
    assert error.value.status_code == 409
    assert await db_session.get(MediaRequest, movie.id)
    deletion.radarr_client.delete_movie.assert_not_awaited()

@pytest.mark.asyncio
async def test_upstream_failure_retains_request_and_skips_downstream(db_session):
    item = await add(db_session, radarr_id=3, jellyfin_id="movie", jellyseerr_id=9)
    deletion.radarr_client.delete_movie.return_value = (False, "offline")
    log = await deletion.delete_request(db_session, item.id)
    assert log.status == DeletionStatus.INCOMPLETE
    assert await db_session.get(MediaRequest, item.id)
    deletion.jellyfin_client.delete_item.assert_not_awaited()
    deletion.jellyseerr_client.delete_request.assert_not_awaited()
    assert not any(e.status.value == "pending" for e in log.sync_events[-3:])

@pytest.mark.asyncio
async def test_downstream_failure_retains_request_for_retry(db_session):
    item = await add(db_session, radarr_id=3, jellyfin_id="movie", jellyseerr_id=9)
    deletion.jellyfin_client.delete_item.return_value = (False, "offline")
    log = await deletion.delete_request(db_session, item.id)
    assert log.status == DeletionStatus.INCOMPLETE
    assert await db_session.get(MediaRequest, item.id)
    deletion.jellyseerr_client.delete_request.assert_not_awaited()
    deletion.jellyfin_client.delete_item.return_value = (True, "already removed")
    log = await deletion.delete_request(db_session, item.id)
    assert log.status == DeletionStatus.COMPLETE
    assert await db_session.get(MediaRequest, item.id) is None

@pytest.mark.asyncio
async def test_keep_files_preserves_availability(db_session):
    item = await add(db_session, radarr_id=3, jellyfin_id="movie", jellyseerr_id=9)
    log = await deletion.delete_request(db_session, item.id, delete_files=False)
    assert log.status == DeletionStatus.COMPLETE
    deletion.radarr_client.delete_movie.assert_awaited_once_with(3, delete_files=False, movie_path="/movies/Synthetic", tmdb_id=123)
    deletion.jellyfin_client.delete_item.assert_not_awaited()
    deletion.jellyseerr_client.delete_media.assert_not_awaited()

@pytest.mark.asyncio
async def test_sync_disabled_only_removes_selected_tracker_record(db_session, monkeypatch):
    monkeypatch.setattr(deletion.settings, "ENABLE_DELETION_SYNC", False)
    item = await add(db_session, MediaType.TV, season=1, sonarr_id=5)
    sibling = await add(db_session, MediaType.TV, season=2, sonarr_id=5)
    log = await deletion.delete_request(db_session, item.id)
    assert log.status == DeletionStatus.COMPLETE
    assert await db_session.get(MediaRequest, item.id) is None
    assert await db_session.get(MediaRequest, sibling.id)
    deletion.sonarr_client.delete_series.assert_not_awaited()

@pytest.mark.asyncio
async def test_path_persisted_before_external_delete(db_session):
    item = await add(db_session, radarr_id=3)
    async def delete(*args, **kwargs):
        await db_session.refresh(item)
        assert item.deletion_movie_path == "/movies/Synthetic"
        return False, "permission denied"
    deletion.radarr_client.delete_movie.side_effect = delete
    log = await deletion.delete_request(db_session, item.id)
    assert log.status == DeletionStatus.INCOMPLETE
    assert await db_session.get(MediaRequest, item.id)

@pytest.mark.asyncio
async def test_jellyfin_scan_acceptance_is_not_removal(db_session):
    item = await add(db_session, radarr_id=3, jellyfin_id="movie", jellyseerr_id=9)
    deletion.jellyfin_client.wait_for_item_removal.return_value = False
    log = await deletion.delete_request(db_session, item.id)
    assert log.status == DeletionStatus.INCOMPLETE
    assert await db_session.get(MediaRequest, item.id)
    deletion.jellyseerr_client.delete_request.assert_not_awaited()

@pytest.mark.asyncio
async def test_jellyseerr_request_failure_does_not_purge_media(db_session):
    item = await add(db_session, radarr_id=3, jellyseerr_id=9)
    deletion.jellyseerr_client.delete_request.return_value = (False, "offline")
    log = await deletion.delete_request(db_session, item.id)
    assert log.status == DeletionStatus.INCOMPLETE
    deletion.jellyseerr_client.delete_media.assert_not_awaited()

@pytest.mark.asyncio
async def test_service_error_is_retained_and_stops_deletion(db_session):
    item = await add(db_session, radarr_id=3, jellyseerr_id=9)
    deletion.radarr_client.get_movie_strict.side_effect = ValueError("unverified")
    log = await deletion.delete_request(db_session, item.id)
    assert log.status == DeletionStatus.INCOMPLETE
    assert await db_session.get(MediaRequest, item.id)
    deletion.radarr_client.delete_movie.assert_not_awaited()
    deletion.jellyseerr_client.delete_request.assert_not_awaited()

@pytest.mark.asyncio
async def test_external_movie_delete_requires_disk_proof(db_session, monkeypatch):
    item = await add(db_session, radarr_id=3, jellyseerr_id=9, final_path="/movies/Synthetic/film.mkv")
    monkeypatch.setattr(deletion.radarr_client, "folder_video_files", AsyncMock(return_value=[item.final_path]))
    log = await deletion.delete_request(db_session, item.id, source=DeletionSource.RADARR, skip_services=["radarr"])
    assert log.status == DeletionStatus.INCOMPLETE
    assert await db_session.get(MediaRequest, item.id)
    deletion.jellyseerr_client.delete_request.assert_not_awaited()

@pytest.mark.asyncio
async def test_jellyseerr_media_reappearing_is_not_complete(db_session):
    item = await add(db_session, radarr_id=3, jellyseerr_id=9)
    deletion.jellyseerr_client.get_media_id_by_tmdb.side_effect = [91, 92]
    log = await deletion.delete_request(db_session, item.id)
    assert log.status == DeletionStatus.INCOMPLETE
    assert await db_session.get(MediaRequest, item.id)

@pytest.mark.asyncio
async def test_radarr_echo_does_not_start_second_deletion(db_session):
    from app.plugins.radarr import RadarrPlugin
    item = await add(db_session, radarr_id=3, jellyseerr_id=9)
    o = deletion.DeletionOrchestrator(db_session)
    await o._create_deletion_log(item, DeletionSource.DASHBOARD, None, "admin")
    await db_session.commit()
    await RadarrPlugin()._handle_movie_delete(item, {"movie": {"id": 3}, "deletedFiles": True}, db_session)
    assert await db_session.get(MediaRequest, item.id)
    assert len((await db_session.execute(select(DeletionLog))).scalars().all()) == 1
    deletion.jellyseerr_client.delete_request.assert_not_awaited()

@pytest.mark.asyncio
async def test_existing_database_migrates_and_retains_retry_path(tmp_path):
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy import text
    from app.database import run_migrations
    engine = create_async_engine("sqlite+aiosqlite:///" + str(tmp_path / "old.db"))
    try:
        async with engine.begin() as conn:
            await conn.execute(text("CREATE TABLE requests (id INTEGER PRIMARY KEY)"))
            await conn.execute(text("INSERT INTO requests (id) VALUES (19)"))
            await run_migrations(conn)
            await conn.execute(text("UPDATE requests SET deletion_movie_path='/movies/Synthetic' WHERE id=19"))
        async with engine.begin() as conn:
            await run_migrations(conn)
            assert (await conn.execute(text("SELECT deletion_movie_path FROM requests WHERE id=19"))).scalar() == "/movies/Synthetic"
    finally: await engine.dispose()
