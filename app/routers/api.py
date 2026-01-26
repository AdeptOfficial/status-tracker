"""REST API endpoints for the dashboard and external access.

Provides:
- Health check
- List/get requests
- Request statistics
- Retry failed/timed out requests
- Delete requests (admin only)
- Deletion logs
"""

import logging
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import MediaRequest, RequestState, DeletionLog, DeletionSource, Episode
from app.plugins import get_all_plugins
from app.core.state_machine import state_machine
from app.core.broadcaster import broadcaster
from app.schemas import (
    HealthResponse,
    MediaRequestResponse,
    MediaRequestWithEpisodesResponse,
    MediaRequestDetailResponse,
    RequestListResponse,
    EpisodeResponse,
    DeleteRequestPayload,
    BulkDeleteRequestPayload,
    DeletionLogResponse,
    DeletionLogDetailResponse,
    DeletionLogListResponse,
    SyncResultResponse,
)
from app.services.auth import (
    AuthenticatedUser,
    require_admin_user,
    get_current_user,
    AUTH_COOKIE_NAME,
)
from app.clients.jellyfin import jellyfin_client
from app.services.deletion_orchestrator import delete_request as do_delete_request
from app.clients.radarr import radarr_client

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["api"])

# Version for health check
VERSION = "0.1.0"


@router.get("/health", response_model=HealthResponse)
async def health_check(db: AsyncSession = Depends(get_db)):
    """
    Health check endpoint.

    Used by Docker healthcheck and monitoring systems.
    Returns service status, version, and loaded plugins.
    """
    # Test database connection
    try:
        await db.execute(select(func.count()).select_from(MediaRequest))
        db_status = "connected"
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        db_status = f"error: {str(e)}"

    # Check Shoko SignalR status
    shoko_status = None
    if settings.ENABLE_SHOKO:
        if settings.SHOKO_API_KEY:
            try:
                from app.clients.shoko import get_shoko_client
                client = get_shoko_client()
                shoko_status = client.state.value
            except Exception as e:
                logger.error(f"Shoko health check failed: {e}")
                shoko_status = "error"
        else:
            shoko_status = "no_api_key"
    else:
        shoko_status = "disabled"

    return HealthResponse(
        status="healthy" if db_status == "connected" else "degraded",
        version=VERSION,
        database=db_status,
        plugins_loaded=[p.name for p in get_all_plugins()],
        shoko_signalr=shoko_status,
    )


@router.get("/requests", response_model=RequestListResponse)
async def list_requests(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    state: Optional[RequestState] = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List media requests with pagination.

    Query params:
    - page: Page number (default 1)
    - per_page: Items per page (default 20, max 100)
    - state: Filter by state (optional)

    Returns most recent requests first.
    """
    # Build query
    stmt = select(MediaRequest)
    count_stmt = select(func.count()).select_from(MediaRequest)

    if state:
        stmt = stmt.where(MediaRequest.state == state)
        count_stmt = count_stmt.where(MediaRequest.state == state)

    # Get total count
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Get paginated results with eager-loaded episodes
    stmt = (
        stmt.options(selectinload(MediaRequest.episodes))
        .order_by(MediaRequest.updated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(stmt)
    requests = result.scalars().all()

    return RequestListResponse(
        requests=[MediaRequestWithEpisodesResponse.model_validate(r) for r in requests],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/requests/active", response_model=list[MediaRequestResponse])
async def list_active_requests(db: AsyncSession = Depends(get_db)):
    """
    List all active (non-terminal) requests.

    Active states: REQUESTED, APPROVED, GRABBING, DOWNLOADING,
                   DOWNLOADED, IMPORTING, ANIME_MATCHING
    """
    active_states = [
        RequestState.REQUESTED,
        RequestState.APPROVED,
        RequestState.GRABBING,
        RequestState.DOWNLOADING,
        RequestState.DOWNLOADED,
        RequestState.IMPORTING,
        RequestState.ANIME_MATCHING,
    ]

    stmt = (
        select(MediaRequest)
        .options(selectinload(MediaRequest.episodes))
        .where(MediaRequest.state.in_(active_states))
        .order_by(MediaRequest.updated_at.desc())
    )

    result = await db.execute(stmt)
    requests = result.scalars().all()

    return [MediaRequestWithEpisodesResponse.model_validate(r) for r in requests]


@router.get("/requests/{request_id}", response_model=MediaRequestDetailResponse)
async def get_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single request with full timeline.

    Returns 404 if request not found.
    """
    stmt = (
        select(MediaRequest)
        .options(
            selectinload(MediaRequest.timeline_events),
            selectinload(MediaRequest.episodes),
        )
        .where(MediaRequest.id == request_id)
    )

    result = await db.execute(stmt)
    request = result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    return MediaRequestDetailResponse.model_validate(request)


@router.get("/requests/{request_id}/episodes", response_model=list[EpisodeResponse])
async def get_request_episodes(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Get all episodes for a TV series request.

    Returns empty list for movies or requests without episodes.
    Returns 404 if request not found.
    """
    # First verify the request exists
    request_stmt = select(MediaRequest).where(MediaRequest.id == request_id)
    request_result = await db.execute(request_stmt)
    request = request_result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    # Get episodes for this request
    stmt = (
        select(Episode)
        .where(Episode.request_id == request_id)
        .order_by(Episode.season_number, Episode.episode_number)
    )

    result = await db.execute(stmt)
    episodes = result.scalars().all()

    return [EpisodeResponse.model_validate(ep) for ep in episodes]


@router.get("/stats")
async def get_stats(db: AsyncSession = Depends(get_db)):
    """
    Get request statistics by state.

    Returns count of requests in each state.
    """
    stmt = (
        select(MediaRequest.state, func.count())
        .group_by(MediaRequest.state)
    )

    result = await db.execute(stmt)
    stats = {row[0].value: row[1] for row in result}

    # Ensure all states are present
    for state in RequestState:
        if state.value not in stats:
            stats[state.value] = 0

    return {"stats": stats, "total": sum(stats.values())}


@router.post("/requests/{request_id}/sync-titles")
async def sync_alternate_titles(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Sync alternate titles from TMDB for anime movies.

    This adds Japanese/alternate titles to Radarr so it can parse
    releases with non-English names. Triggers a search after sync.

    Useful for anime movies that can't grab releases due to title mismatch.
    """
    import json

    stmt = select(MediaRequest).where(MediaRequest.id == request_id)
    result = await db.execute(stmt)
    request = result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if not request.tmdb_id:
        raise HTTPException(status_code=400, detail="Request has no TMDB ID")

    # Look up movie in Radarr
    movie = await radarr_client.get_movie_by_tmdb(request.tmdb_id)
    if not movie:
        raise HTTPException(
            status_code=404,
            detail="Movie not found in Radarr. Add it to Radarr first."
        )

    radarr_id = movie.get("id")
    title = movie.get("title", request.title)

    # Fetch alternate titles from TMDB via Radarr lookup
    lookup_data = await radarr_client.lookup_movie(request.tmdb_id)
    if not lookup_data:
        raise HTTPException(
            status_code=500,
            detail="Could not lookup movie from TMDB"
        )

    # Get alternate titles from lookup
    lookup_titles = lookup_data.get("alternateTitles", [])
    if not lookup_titles:
        return {
            "success": True,
            "message": "No alternate titles found in TMDB",
            "titles_added": 0,
        }

    # Extract title strings
    title_strings = [t.get("title") for t in lookup_titles if t.get("title")]

    # Add them to Radarr
    success = await radarr_client.add_alternate_titles(radarr_id, title_strings)
    if not success:
        raise HTTPException(
            status_code=500,
            detail="Failed to add alternate titles to Radarr"
        )

    # Store in our database
    request.alternate_titles = json.dumps(title_strings)
    request.is_anime = True
    request.radarr_id = radarr_id
    await db.commit()

    # Try to search and grab automatically
    grabbed = await radarr_client.search_and_grab_anime(radarr_id, title_strings)

    if not grabbed:
        # Fallback to just triggering search
        await radarr_client.trigger_search(radarr_id)

    logger.info(
        f"Synced {len(title_strings)} alternate titles for '{title}' "
        f"(grabbed: {grabbed})"
    )

    # Get release info for debugging
    releases = await radarr_client.search_releases(radarr_id)
    release_info = []
    for r in releases[:5]:
        release_info.append({
            "title": r.get("title", "")[:60],
            "approved": r.get("approved", False),
            "rejections": r.get("rejections", [])[:3],
        })

    return {
        "success": True,
        "message": f"Added {len(title_strings)} alternate titles",
        "titles_added": len(title_strings),
        "grabbed": grabbed,
        "titles": title_strings[:10],
        "releases_found": len(releases),
        "sample_releases": release_info,
    }


@router.post("/requests/{request_id}/retry", response_model=MediaRequestResponse)
async def retry_request(
    request_id: int,
    db: AsyncSession = Depends(get_db),
):
    """
    Retry a failed or timed out request.

    This resets the request back to APPROVED state so it can be
    re-grabbed by Sonarr/Radarr. Uses APPROVED (not REQUESTED) because
    the state machine only allows FAILED/TIMEOUT -> APPROVED transitions.

    Only works for requests in FAILED or TIMEOUT states.
    """
    stmt = select(MediaRequest).where(MediaRequest.id == request_id)
    result = await db.execute(stmt)
    request = result.scalar_one_or_none()

    if not request:
        raise HTTPException(status_code=404, detail="Request not found")

    if request.state not in (RequestState.FAILED, RequestState.TIMEOUT):
        raise HTTPException(
            status_code=400,
            detail=f"Cannot retry request in {request.state.value} state. "
                   f"Only failed or timed out requests can be retried."
        )

    # Transition back to APPROVED (state machine allows FAILED/TIMEOUT -> APPROVED)
    success = await state_machine.transition(
        request,
        RequestState.APPROVED,
        db,
        service="api",
        event_type="Retry",
        details=f"Retried from {request.state.value} state",
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to retry request")

    await db.commit()
    await broadcaster.broadcast_update(request)

    logger.info(f"Request {request_id} ({request.title}) retried")

    return MediaRequestResponse.model_validate(request)


# ============================================
# Deletion Endpoints (Admin Only)
# ============================================


@router.post("/requests/{request_id}/delete", response_model=DeletionLogResponse)
async def delete_request(
    request_id: int,
    payload: DeleteRequestPayload,
    user: AuthenticatedUser = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete a media request and sync to external services.

    Requires admin privileges (X-Jellyfin-Token header).

    This will:
    1. Create a DeletionLog entry (audit trail)
    2. Hard delete the request from the database
    3. Delete from Sonarr/Radarr (if delete_files=true, deletes files from disk)
    4. Remove from Jellyfin library
    5. Remove from Jellyseerr
    6. Trigger Shoko rescan (for anime)

    The request will be completely removed from status-tracker.
    If the same media is requested again later, it will be a new request.
    """
    deletion_log = await do_delete_request(
        db=db,
        request_id=request_id,
        user_id=user.user_id,
        username=user.username,
        delete_files=payload.delete_files,
        source=DeletionSource.DASHBOARD,
    )

    if not deletion_log:
        raise HTTPException(status_code=404, detail="Request not found")

    logger.info(
        f"Request {request_id} deleted by {user.username} "
        f"(delete_files={payload.delete_files})"
    )

    return DeletionLogResponse.model_validate(deletion_log)


@router.post("/requests/bulk-delete", response_model=list[DeletionLogResponse])
async def bulk_delete_requests(
    payload: BulkDeleteRequestPayload,
    user: AuthenticatedUser = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Delete multiple requests at once.

    Requires admin privileges (X-Jellyfin-Token header).

    Returns list of DeletionLog entries for each successfully deleted request.
    Requests that are not found are silently skipped.
    """
    results = []

    for request_id in payload.request_ids:
        deletion_log = await do_delete_request(
            db=db,
            request_id=request_id,
            user_id=user.user_id,
            username=user.username,
            delete_files=payload.delete_files,
            source=DeletionSource.DASHBOARD,
        )

        if deletion_log:
            results.append(DeletionLogResponse.model_validate(deletion_log))
            logger.info(f"Bulk delete: Request {request_id} deleted by {user.username}")

    return results


@router.get("/deletion-logs", response_model=DeletionLogListResponse)
async def list_deletion_logs(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    source: Optional[DeletionSource] = None,
    user: AuthenticatedUser = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List deletion logs with pagination.

    Requires admin privileges (X-Jellyfin-Token header).

    Query params:
    - page: Page number (default 1)
    - per_page: Items per page (default 20, max 100)
    - source: Filter by deletion source (optional)

    Returns most recent deletions first.
    """
    # Build query
    stmt = select(DeletionLog)
    count_stmt = select(func.count()).select_from(DeletionLog)

    if source:
        stmt = stmt.where(DeletionLog.source == source)
        count_stmt = count_stmt.where(DeletionLog.source == source)

    # Get total count
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Get paginated results
    stmt = (
        stmt.order_by(DeletionLog.initiated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(stmt)
    logs = result.scalars().all()

    return DeletionLogListResponse(
        logs=[DeletionLogResponse.model_validate(log) for log in logs],
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/deletion-logs/{log_id}", response_model=DeletionLogDetailResponse)
async def get_deletion_log(
    log_id: int,
    user: AuthenticatedUser = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get a single deletion log with full sync event timeline.

    Requires admin privileges (X-Jellyfin-Token header).

    Returns 404 if deletion log not found.
    """
    stmt = (
        select(DeletionLog)
        .options(selectinload(DeletionLog.sync_events))
        .where(DeletionLog.id == log_id)
    )

    result = await db.execute(stmt)
    log = result.scalar_one_or_none()

    if not log:
        raise HTTPException(status_code=404, detail="Deletion log not found")

    return DeletionLogDetailResponse.model_validate(log)


@router.get("/requests/{request_id}/delete-preview")
async def preview_delete(
    request_id: int,
    user: AuthenticatedUser = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Preview what would be deleted without actually deleting.

    Requires admin privileges (X-Jellyfin-Token header).

    Useful for confirmation dialogs to show the user what services
    will be affected by the deletion.
    """
    from app.services.deletion_orchestrator import DeletionOrchestrator

    orchestrator = DeletionOrchestrator(db)
    preview = await orchestrator.preview_deletion(request_id)

    if not preview:
        raise HTTPException(status_code=404, detail="Request not found")

    return preview


@router.get("/auth/session")
async def get_auth_session(
    user: Optional[AuthenticatedUser] = Depends(get_current_user),
):
    """
    Get current authentication session info.

    Returns user info if authenticated, or null if not.
    Useful for checking auth status and admin privileges from frontend.
    """
    if not user:
        return {"authenticated": False}

    return {
        "authenticated": True,
        "user_id": user.user_id,
        "username": user.username,
        "is_admin": user.is_admin,
    }


@router.post("/auth/login")
async def login(
    response: Response,
    username: str = Query(...),
    password: str = Query(...),
):
    """
    Authenticate with Jellyfin and set session cookie.

    Args:
        username: Jellyfin username
        password: Jellyfin password

    Returns:
        User info if successful, error otherwise.
        Also sets HTTP-only cookie with Jellyfin token.
    """
    result = await jellyfin_client.authenticate(username, password)

    if not result.success:
        raise HTTPException(
            status_code=401,
            detail=result.error or "Authentication failed"
        )

    # Set HTTP-only cookie for page loads
    response.set_cookie(
        key=AUTH_COOKIE_NAME,
        value=result.token,
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 7,  # 7 days
    )

    return {
        "success": True,
        "user_id": result.user.user_id,
        "username": result.user.username,
        "is_admin": result.user.is_admin,
        "token": result.token,  # Also return token for localStorage
    }


@router.post("/auth/logout")
async def logout(response: Response):
    """
    Clear authentication session.

    Removes the HTTP-only cookie.
    Frontend should also clear localStorage token.
    """
    response.delete_cookie(key=AUTH_COOKIE_NAME)
    return {"success": True, "message": "Logged out"}


# ============================================
# Library Sync Endpoints (Admin Only)
# ============================================


@router.post("/admin/sync/library", response_model=SyncResultResponse)
async def sync_library(
    user: AuthenticatedUser = Depends(require_admin_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Sync existing library content from Jellyfin to status-tracker.

    Requires admin privileges (X-Jellyfin-Token header).

    This will:
    1. Trigger a Jellyfin library rescan (ensures fresh data)
    2. Fetch all items from Jellyfin (source of truth)
    3. Filter out items already tracked in status-tracker
    4. Enrich with Radarr/Sonarr IDs for full correlation
    5. Create AVAILABLE entries for each untracked item

    Items that were manually added to the library (not via Jellyseerr)
    will now appear in the dashboard with all metadata populated.
    """
    from app.services.library_sync import LibrarySyncService

    logger.info(f"Library sync initiated by {user.username}")

    sync_service = LibrarySyncService(db)
    result = await sync_service.sync_available_content()

    logger.info(
        f"Library sync complete: {result.added} added, "
        f"{result.skipped} skipped, {result.errors} errors"
    )

    return SyncResultResponse(
        total_scanned=result.total_scanned,
        added=result.added,
        updated=result.updated,
        skipped=result.skipped,
        errors=result.errors,
        error_details=result.error_details,
    )


@router.post("/admin/force-library-scan")
async def force_library_scan(
    user: AuthenticatedUser = Depends(require_admin_user),
):
    """
    Force a Jellyfin library scan.

    Triggers Shokofin VFS regeneration without needing stuck requests.
    Used by n8n workflow for SignalR recovery.
    """
    await jellyfin_client.trigger_library_scan()
    logger.info(f"Library scan triggered by {user.username}")
    return {"success": True, "message": "Library scan triggered"}
