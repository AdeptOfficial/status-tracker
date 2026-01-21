"""SSE (Server-Sent Events) endpoint for real-time dashboard updates.

Why SSE over WebSocket?
- One-way server→client is exactly what we need (status updates)
- Native browser support with auto-reconnect
- htmx has a dedicated extension for it
- Simpler to implement and debug

Usage in templates:
    <div hx-ext="sse" sse-connect="/api/sse">
        <div sse-swap="update" hx-swap="innerHTML">...</div>
    </div>
"""

import logging
from fastapi import APIRouter
from sse_starlette.sse import EventSourceResponse

from app.core.broadcaster import broadcaster

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["sse"])


@router.get("/sse")
async def sse_endpoint():
    """
    SSE endpoint for real-time updates.

    Clients connect here and receive events when:
    - Request state changes (state_change)
    - Download progress updates (progress_update)
    - New requests are created (new_request)

    Event format:
        event: update
        data: {"event_type": "state_change", "request_id": 1, "request": {...}}

    The htmx SSE extension handles this automatically when templates use:
        sse-connect="/api/sse"
        sse-swap="update"
    """

    async def event_generator():
        """Generate SSE events from broadcaster."""
        logger.info("SSE client connecting...")

        # Send initial keepalive (helps with proxy timeouts)
        yield {
            "event": "connected",
            "data": '{"status": "connected"}',
        }

        # Subscribe and yield events
        async for message in broadcaster.subscribe():
            # broadcaster already formats as SSE string, but sse-starlette
            # expects dict with event/data keys, so we parse it
            # Actually, the broadcaster yields raw SSE strings like:
            #   "event: update\ndata: {...}\n\n"
            # We need to convert that to the format sse-starlette expects
            lines = message.strip().split("\n")
            event_name = "message"
            data = ""

            for line in lines:
                if line.startswith("event: "):
                    event_name = line[7:]
                elif line.startswith("data: "):
                    data = line[6:]

            yield {
                "event": event_name,
                "data": data,
            }

    return EventSourceResponse(event_generator())


@router.get("/sse/status")
async def sse_status():
    """Check SSE connection status and client count."""
    return {
        "connected_clients": broadcaster.client_count,
        "status": "healthy",
    }
