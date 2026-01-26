"""State machine for managing request lifecycle transitions.

Handles state changes with validation and timeline event creation.
"""

import json
import logging
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from app.models import RequestState, TimelineEvent

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models import MediaRequest

logger = logging.getLogger(__name__)

# Valid state transitions
# Key: current state, Value: list of valid next states
#
# Special cases:
# - APPROVED → AVAILABLE: Content already exists in library (no download needed)
# - GRABBING → IMPORTING: When qBittorrent polling isn't active
# - When qBit plugin is active, normal flow is GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING
VALID_TRANSITIONS: dict[RequestState, list[RequestState]] = {
    RequestState.REQUESTED: [RequestState.APPROVED, RequestState.FAILED],
    RequestState.APPROVED: [RequestState.GRABBING, RequestState.AVAILABLE, RequestState.FAILED],
    RequestState.GRABBING: [RequestState.DOWNLOADING, RequestState.IMPORTING, RequestState.FAILED],
    RequestState.DOWNLOADING: [
        RequestState.DOWNLOADED,
        RequestState.FAILED,
        RequestState.TIMEOUT,
    ],
    RequestState.DOWNLOADED: [RequestState.IMPORTING, RequestState.ANIME_MATCHING, RequestState.AVAILABLE, RequestState.FAILED],
    RequestState.IMPORTING: [
        RequestState.AVAILABLE,
        RequestState.ANIME_MATCHING,  # Shoko detects anime file
        RequestState.FAILED,
        RequestState.TIMEOUT,
    ],
    RequestState.ANIME_MATCHING: [RequestState.AVAILABLE, RequestState.MATCH_FAILED, RequestState.FAILED],
    RequestState.AVAILABLE: [RequestState.FAILED],  # Can fail after available (manual override)
    RequestState.MATCH_FAILED: [RequestState.ANIME_MATCHING, RequestState.AVAILABLE],  # After manual link in Shoko
    RequestState.FAILED: [RequestState.APPROVED],  # Can retry from APPROVED
    RequestState.TIMEOUT: [RequestState.APPROVED],  # Can retry from APPROVED
}


class StateMachine:
    """
    Manages state transitions for media requests.

    Usage:
        sm = StateMachine()
        await sm.transition(request, RequestState.GRABBING, db, ...)
    """

    def __init__(self):
        self._listeners: list = []

    def can_transition(
        self, current: RequestState, target: RequestState
    ) -> bool:
        """Check if transition from current to target state is valid."""
        valid_next = VALID_TRANSITIONS.get(current, [])
        return target in valid_next

    async def transition(
        self,
        request: "MediaRequest",
        new_state: RequestState,
        db: "AsyncSession",
        service: str,
        event_type: str,
        details: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> bool:
        """
        Transition a request to a new state.

        Args:
            request: The MediaRequest to transition
            new_state: Target state
            db: Database session
            service: Name of service triggering the change (e.g., 'sonarr')
            event_type: Type of event (e.g., 'Grab', 'Download')
            details: Human-readable details for timeline
            raw_data: Raw webhook data for debugging

        Returns:
            True if transition was successful, False if invalid/blocked.
        """
        old_state = request.state

        # Validate transition
        if not self.can_transition(old_state, new_state):
            logger.warning(
                f"Invalid transition for request {request.id}: "
                f"{old_state.value} -> {new_state.value}"
            )
            return False

        # Update request state
        request.state = new_state
        request.state_changed_at = datetime.utcnow()
        request.updated_at = datetime.utcnow()

        # Create timeline event
        event = TimelineEvent(
            request_id=request.id,
            service=service,
            event_type=event_type,
            state=new_state,
            details=details,
            raw_data=json.dumps(raw_data) if raw_data else None,
            timestamp=datetime.utcnow(),
        )
        db.add(event)

        logger.info(
            f"Request {request.id} ({request.title}): "
            f"{old_state.value} -> {new_state.value} via {service}"
        )

        # Notify listeners
        for listener in self._listeners:
            try:
                await listener(request, old_state, new_state)
            except Exception as e:
                logger.error(f"State change listener error: {e}")

        return True

    async def add_event(
        self,
        request: "MediaRequest",
        db: "AsyncSession",
        service: str,
        event_type: str,
        details: Optional[str] = None,
        raw_data: Optional[dict] = None,
    ) -> TimelineEvent:
        """
        Add a timeline event without changing state.

        Useful for progress updates or informational events.
        """
        event = TimelineEvent(
            request_id=request.id,
            service=service,
            event_type=event_type,
            state=request.state,
            details=details,
            raw_data=json.dumps(raw_data) if raw_data else None,
            timestamp=datetime.utcnow(),
        )
        db.add(event)
        request.updated_at = datetime.utcnow()
        return event


# Global instance
state_machine = StateMachine()
