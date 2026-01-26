"""HTML page routes for the web dashboard.

Serves Jinja2 templates with htmx support.
"""

import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, Request, HTTPException, Query
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func, distinct
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.config import settings
from app.database import get_db
from app.models import MediaRequest, RequestState, DeletionLog
from app.services.auth import get_current_user, AuthenticatedUser

logger = logging.getLogger(__name__)

router = APIRouter(tags=["pages"])

# Setup Jinja2 templates
# Path is relative to where uvicorn runs (app directory)
templates_dir = Path(__file__).parent.parent / "templates"
templates = Jinja2Templates(directory=str(templates_dir))


@router.get("/login", response_class=HTMLResponse)
async def login_page(
    request: Request,
    next: Optional[str] = Query(None),
    user: Optional[AuthenticatedUser] = Depends(get_current_user),
):
    """
    Login page.

    If user is already authenticated, redirects to home or 'next' param.
    """
    # If already logged in, redirect
    if user:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url=next or "/", status_code=303)

    return templates.TemplateResponse(
        "login.html",
        {
            "request": request,
            "active_page": None,
            "is_admin": False,
            "current_user": None,
        },
    )


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Optional[AuthenticatedUser] = Depends(get_current_user),
):
    """
    Main dashboard page - shows all active requests.

    Active = any state except AVAILABLE, FAILED, TIMEOUT (terminal states).
    """
    active_states = [
        RequestState.REQUESTED,
        RequestState.APPROVED,
        RequestState.GRABBING,
        RequestState.DOWNLOADING,
        RequestState.DOWNLOADED,
        RequestState.IMPORTING,
        RequestState.ANIME_MATCHING,
        RequestState.MATCH_FAILED,  # Show in UI so users can notify admin
    ]

    stmt = (
        select(MediaRequest)
        .options(selectinload(MediaRequest.episodes))
        .where(MediaRequest.state.in_(active_states))
        .order_by(MediaRequest.updated_at.desc())
    )

    result = await db.execute(stmt)
    requests = result.scalars().all()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,  # Required by Jinja2
            "requests": requests,
            "active_page": "home",
            "is_admin": user.is_admin if user else False,
            "current_user": user,
        },
    )


@router.get("/history", response_class=HTMLResponse)
async def history(
    request: Request,
    user_filter: Optional[str] = Query(None, alias="user"),
    state_filter: Optional[str] = Query(None, alias="state"),
    db: AsyncSession = Depends(get_db),
    auth_user: Optional[AuthenticatedUser] = Depends(get_current_user),
):
    """
    History page - shows completed and failed requests.

    Terminal states: AVAILABLE, FAILED, TIMEOUT

    Supports filtering by:
    - user: username query param
    - state: state query param (available, failed, timeout)
    """
    terminal_states = [
        RequestState.AVAILABLE,
        RequestState.FAILED,
        RequestState.TIMEOUT,
    ]

    # Build base query with eager loading for episodes (used by card.html)
    stmt = select(MediaRequest).options(selectinload(MediaRequest.episodes))

    # Apply state filter if provided (otherwise show all terminal states)
    if state_filter and state_filter in ['available', 'failed', 'timeout']:
        stmt = stmt.where(MediaRequest.state == RequestState(state_filter))
    else:
        stmt = stmt.where(MediaRequest.state.in_(terminal_states))

    # Apply user filter if provided
    if user_filter:
        stmt = stmt.where(MediaRequest.requested_by == user_filter)

    stmt = stmt.order_by(MediaRequest.updated_at.desc()).limit(100)

    result = await db.execute(stmt)
    requests = result.scalars().all()

    # Get list of unique users for filter dropdown
    users_stmt = (
        select(distinct(MediaRequest.requested_by))
        .where(MediaRequest.requested_by.isnot(None))
        .where(MediaRequest.state.in_(terminal_states))
    )
    users_result = await db.execute(users_stmt)
    users = [u for u in users_result.scalars().all() if u]

    # Get stats for summary cards
    stats_stmt = (
        select(MediaRequest.state, func.count())
        .where(MediaRequest.state.in_(terminal_states))
        .group_by(MediaRequest.state)
    )
    stats_result = await db.execute(stats_stmt)
    stats = {row[0].value: row[1] for row in stats_result}

    return templates.TemplateResponse(
        "history.html",
        {
            "request": request,
            "requests": requests,
            "users": sorted(users),
            "current_user_filter": user_filter,
            "current_state_filter": state_filter,
            "stats": stats,
            "active_page": "history",
            "is_admin": auth_user.is_admin if auth_user else False,
            "current_user": auth_user,
            "deletion_sync_enabled": settings.ENABLE_DELETION_SYNC,
        },
    )


@router.get("/request/{request_id}", response_class=HTMLResponse)
async def request_detail(
    request: Request,
    request_id: int,
    db: AsyncSession = Depends(get_db),
    user: Optional[AuthenticatedUser] = Depends(get_current_user),
):
    """
    Single request detail page with timeline.

    Shows:
    - Media info (title, poster, quality)
    - Current status with progress
    - Full timeline of events
    - Delete button (admin only)
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
    media_request = result.scalar_one_or_none()

    if not media_request:
        raise HTTPException(status_code=404, detail="Request not found")

    # Sort timeline events by timestamp (oldest first for display)
    timeline_events = sorted(
        media_request.timeline_events,
        key=lambda e: e.timestamp,
    )

    return templates.TemplateResponse(
        name="detail.html",
        context={
            "request": request,  # Required by Starlette
            "media_request": media_request,  # MediaRequest object for template
            "timeline_events": timeline_events,
            "jellyfin_url": settings.JELLYFIN_URL,
            "active_page": None,
            "is_admin": user.is_admin if user else False,
            "current_user": user,
            "deletion_sync_enabled": settings.ENABLE_DELETION_SYNC,
        },
    )


@router.get("/status", response_class=HTMLResponse)
async def status_page(
    request: Request,
    db: AsyncSession = Depends(get_db),
    user: Optional[AuthenticatedUser] = Depends(get_current_user),
):
    """
    System status page - shows health and connection status.

    Displays:
    - Overall system health
    - Database connection status
    - Loaded plugins
    - Shoko SignalR connection status
    - API endpoint reference
    """
    from sqlalchemy import func

    # Build health data (same logic as /api/health)
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

    # Get loaded plugins
    from app.plugins import get_all_plugins
    plugins = [p.name for p in get_all_plugins()]

    health = {
        "status": "healthy" if db_status == "connected" else "degraded",
        "version": "0.1.0",
        "database": db_status,
        "plugins_loaded": plugins,
        "shoko_signalr": shoko_status,
    }

    return templates.TemplateResponse(
        "status.html",
        {
            "request": request,
            "health": health,
            "active_page": "status",
            "is_admin": user.is_admin if user else False,
            "current_user": user,
        },
    )


@router.get("/deletion-logs", response_class=HTMLResponse)
async def deletion_logs_page(
    request: Request,
    page: int = Query(1, ge=1),
    source_filter: Optional[str] = Query(None, alias="source"),
    db: AsyncSession = Depends(get_db),
    user: Optional[AuthenticatedUser] = Depends(get_current_user),
):
    """
    Deletion logs page - shows audit trail of deleted media.

    Admin only. Redirects non-admins to home page.
    """
    # Check if user is admin
    if not user or not user.is_admin:
        # Redirect to home with error message
        from fastapi.responses import RedirectResponse
        return RedirectResponse(url="/", status_code=303)

    from app.models import DeletionSource
    from sqlalchemy.orm import selectinload

    # Build query
    stmt = select(DeletionLog).options(selectinload(DeletionLog.sync_events))

    # Apply source filter if provided
    valid_sources = [s.value for s in DeletionSource]
    if source_filter and source_filter in valid_sources:
        stmt = stmt.where(DeletionLog.source == DeletionSource(source_filter))

    # Get paginated results
    per_page = 20
    stmt = (
        stmt.order_by(DeletionLog.initiated_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )

    result = await db.execute(stmt)
    logs = result.scalars().all()

    # Get total count for pagination
    count_stmt = select(func.count()).select_from(DeletionLog)
    if source_filter and source_filter in valid_sources:
        count_stmt = count_stmt.where(DeletionLog.source == DeletionSource(source_filter))
    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0

    # Calculate pagination info
    total_pages = (total + per_page - 1) // per_page

    # Get stats by source
    stats_stmt = (
        select(DeletionLog.source, func.count())
        .group_by(DeletionLog.source)
    )
    stats_result = await db.execute(stats_stmt)
    source_stats = {row[0].value: row[1] for row in stats_result}

    return templates.TemplateResponse(
        "deletion-logs.html",
        {
            "request": request,
            "logs": logs,
            "source_stats": source_stats,
            "current_source_filter": source_filter,
            "page": page,
            "total_pages": total_pages,
            "total": total,
            "active_page": "deletion-logs",
            "is_admin": True,
            "current_user": user,
        },
    )
