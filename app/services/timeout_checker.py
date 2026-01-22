"""Timeout checker - detects requests stuck in states too long.

This background service periodically checks for requests that have been in certain
"active" states longer than expected. When found, it marks them as TIMEOUT.

WHY? Downloads can stall, imports can hang, and we don't want requests sitting
forever without visibility. The timeout allows users to see something's wrong
and potentially retry.

ALTERNATIVE APPROACH: Could use Celery or a job queue for more robust scheduling,
but that adds complexity. For a homelab, a simple asyncio loop is sufficient.
"""

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from app.config import settings
from app.models import MediaRequest, RequestState
from app.core.state_machine import state_machine
from app.core.broadcaster import broadcaster

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


def get_state_timeouts() -> dict[RequestState, int]:
    """
    Get timeout thresholds per state (in minutes).

    Uses config values where available, defaults for others.
    These are generous defaults - can be tuned based on your typical download sizes.
    """
    return {
        RequestState.DOWNLOADING: settings.DOWNLOADING_TIMEOUT,
        RequestState.IMPORTING: settings.IMPORTING_TIMEOUT,
        RequestState.ANIME_MATCHING: 30,    # 30 min - Shoko matching
        RequestState.DOWNLOADED: 30,        # 30 min - waiting for import
        RequestState.GRABBING: 60,          # 1 hour - waiting for download to start
        RequestState.APPROVED: 120,         # 2 hours - waiting for indexer grab
    }


async def check_timeouts(db: "AsyncSession") -> list[MediaRequest]:
    """
    Check for requests that have been stuck in a state too long.

    Returns list of requests that were timed out.
    """
    timed_out = []
    now = datetime.utcnow()
    state_timeouts = get_state_timeouts()

    for state, timeout_minutes in state_timeouts.items():
        # Calculate cutoff time
        cutoff = now - timedelta(minutes=timeout_minutes)

        # Find stuck requests
        stmt = (
            select(MediaRequest)
            .where(MediaRequest.state == state)
            .where(MediaRequest.state_changed_at < cutoff)
        )

        result = await db.execute(stmt)
        stuck_requests = result.scalars().all()

        for request in stuck_requests:
            time_in_state = (now - request.state_changed_at).total_seconds() / 60
            logger.warning(
                f"Timeout: {request.title} stuck in {state.value} "
                f"for {time_in_state:.0f} minutes (threshold: {timeout_minutes})"
            )

            # Transition to TIMEOUT
            success = await state_machine.transition(
                request,
                RequestState.TIMEOUT,
                db,
                service="timeout_checker",
                event_type="Timeout",
                details=f"Stuck in {state.value} for {time_in_state:.0f} minutes",
            )

            if success:
                timed_out.append(request)

    if timed_out:
        await db.commit()
        # Broadcast AFTER commit so frontend fetches committed data
        for request in timed_out:
            await broadcaster.broadcast_update(request)
        logger.info(f"Timed out {len(timed_out)} stuck requests")

    return timed_out
