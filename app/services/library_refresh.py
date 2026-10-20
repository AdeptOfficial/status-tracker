"""Persistent, bounded Jellyfin refresh recovery. Never deletes media or VFS entries.

The application's single fallback worker owns dispatch; event handlers only insert
idempotent intents. Attempts are committed before HTTP so restart cannot reset them.
"""
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, func
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.orm import selectinload
from app.models import LibraryRefreshJob, MediaRequest, EpisodeState, RequestState, MediaType
from app.config import settings
from app.clients.jellyfin import jellyfin_client
from app.clients.shoko import shoko_http_client

logger = logging.getLogger(__name__)
DEBOUNCE_SECONDS = 30
MIN_SCAN_INTERVAL_SECONDS = 120
MAX_ATTEMPTS = 4
_lock = asyncio.Lock()
ACTIVE = {RequestState.IMPORTING, RequestState.ANIME_MATCHING, RequestState.MATCH_FAILED}


async def queue_refresh(db, request_id, file_id, episode_id=None, now=None):
    if not isinstance(file_id, int) or file_id <= 0:
        return False
    now = now or datetime.utcnow()
    key = f"{request_id}:{episode_id or 0}:{file_id}"
    result = await db.execute(insert(LibraryRefreshJob).values(
        id=key, request_id=request_id, episode_id=episode_id, file_id=file_id,
        status="pending", attempts=0,
        next_attempt_at=now + timedelta(seconds=DEBOUNCE_SECONDS),
    ).on_conflict_do_nothing(index_elements=["id"]))
    return result.rowcount == 1


async def recover_matched_files(request, db):
    """Find missed events by imported paths; an ID alone is not match evidence."""
    if not settings.ENABLE_SHOKO or not settings.SHOKO_API_KEY:
        return
    if not request.is_anime or request.state not in ACTIVE:
        return
    targets = request.episodes if request.media_type == MediaType.TV else [request]
    for target in targets:
        if target.state.value not in {"importing", "anime_matching", "match_failed"} or not target.final_path:
            continue
        episode_id = target.id if request.media_type == MediaType.TV else None
        # Confirm the current file before deduplication. An old terminal job must
        # not suppress a replacement file whose SignalR event was missed.
        file_id = await shoko_http_client.confirmed_file_for_path(target.final_path)
        if file_id and await queue_refresh(db, request.id, file_id, episode_id):
            logger.info("[LIBRARY REFRESH] Recovered confirmed match for request %s episode %s", request.id, episode_id)



async def process_refresh_queue(db, now=None):
    """Verify first, then dispatch at most one scan for all due confirmed files."""
    from app.services.jellyfin_verifier import verify_request
    from app.core.broadcaster import broadcaster
    if not settings.ENABLE_SHOKO or not settings.JELLYFIN_API_KEY:
        return
    async with _lock:
        now = now or datetime.utcnow()
        jobs = list((await db.scalars(select(LibraryRefreshJob).where(
            LibraryRefreshJob.status == "pending", LibraryRefreshJob.next_attempt_at <= now,
        ))).all())
        if not jobs:
            return
        # Verification can mutate/commit request state. Commit each successful
        # request independently and reload after rollback so one malformed item
        # cannot expire shared ORM objects or starve the rest of the batch.
        request_ids = sorted({job.request_id for job in jobs})
        failed = set()
        for request_id in request_ids:
            request = await db.scalar(select(MediaRequest).options(
                selectinload(MediaRequest.episodes)
            ).where(MediaRequest.id == request_id).execution_options(populate_existing=True))
            if request is None or request.state not in ACTIVE:
                continue
            try:
                verified = await verify_request(request, db)
                await db.commit()
            except Exception as exc:
                logger.warning("[LIBRARY REFRESH] Verification failed for request %s (%s)", request_id, type(exc).__name__)
                await db.rollback()
                failed.add(request_id)
                continue
            if verified:
                try:
                    await broadcaster.broadcast_update(request)
                except Exception as exc:
                    logger.warning("[LIBRARY REFRESH] Broadcast failed for request %s (%s)", request_id, type(exc).__name__)
        jobs = list((await db.scalars(select(LibraryRefreshJob).where(
            LibraryRefreshJob.status == "pending", LibraryRefreshJob.next_attempt_at <= now,
        ).execution_options(populate_existing=True))).all())
        requests = list((await db.scalars(select(MediaRequest).options(
            selectinload(MediaRequest.episodes)
        ).where(MediaRequest.id.in_({j.request_id for j in jobs})).execution_options(populate_existing=True))).all())
        by_id = {r.id: r for r in requests}
        due = []
        for job in jobs:
            if job.request_id in failed:
                job.last_error = "verification_failed"
                job.next_attempt_at = now + timedelta(seconds=MIN_SCAN_INTERVAL_SECONDS)
                continue
            request = by_id.get(job.request_id)
            episode = next((e for e in request.episodes if e.id == job.episode_id), None) if request else None
            if request is None or (job.episode_id and episode is None):
                job.status = "cancelled"
            elif (episode and episode.state == EpisodeState.AVAILABLE) or (not job.episode_id and request.state == RequestState.AVAILABLE):
                job.status = "done"
            elif request.state not in ACTIVE and request.state != RequestState.AVAILABLE:
                job.status = "cancelled"
            elif job.attempts >= MAX_ATTEMPTS:
                job.status = "exhausted"
                job.last_error = "availability_not_confirmed"
                logger.warning("[LIBRARY REFRESH] Retry limit reached for request %s file %s", job.request_id, job.file_id)
            else:
                due.append(job)
        await db.commit()
        if not due:
            return
        last = await db.scalar(select(func.max(LibraryRefreshJob.last_attempt_at)))
        if last and now < last + timedelta(seconds=MIN_SCAN_INTERVAL_SECONDS):
            return
        state = await jellyfin_client.library_scan_state()
        if state in {"Running", "Cancelling"}:
            for job in due:
                job.next_attempt_at = now + timedelta(seconds=30)
            await db.commit()
            return
        for job in due:
            job.attempts += 1
            job.last_attempt_at = now
            job.next_attempt_at = now + timedelta(seconds=MIN_SCAN_INTERVAL_SECONDS * 2 ** (job.attempts - 1))
            job.last_error = "dispatch_interrupted" if state == "Idle" else "scan_status_unavailable"
        await db.commit()  # Reserve before HTTP, including failures and process termination.
        # Preview can see new files while the VFS generation cache still
        # describes an earlier scan. Clear memory caches, wait for completion,
        # then scan. Never run either operation over an active library scan.
        cache_ready = state == "Idle" and await jellyfin_client.clear_shoko_discovery_cache()
        success = cache_ready and await jellyfin_client.trigger_library_scan()
        for job in due:
            job.last_error = None if success else (
                "scan_status_unavailable" if state != "Idle" else
                "cache_refresh_unavailable" if not cache_ready else "refresh_rejected")
        await db.commit()
        logger.info("[LIBRARY REFRESH] %s for %s confirmed files (request IDs %s)",
                    "Refresh accepted" if success else "Refresh deferred/failed", len(due),
                    sorted({j.request_id for j in due}))
