# Feature: SSE Live Updates

**Status:** Planned
**Priority:** Medium (after core flow fixes)
**Complexity:** Low

---

## Problem

Currently, users must refresh the page to see download progress updates. This creates a poor UX during active downloads.

---

## Solution

Use Server-Sent Events (SSE) to push real-time updates from server to browser.

```
┌─────────┐                    ┌─────────┐
│ Browser │ ── GET /events ──► │ Server  │
│         │ ◄── keeps open ─── │         │
│         │                    │         │
│         │ ◄── data: {...} ── │ (progress update) │
│         │ ◄── data: {...} ── │ (state change)    │
└─────────┘                    └─────────┘
```

---

## Why SSE Over WebSocket

| Aspect | SSE | WebSocket |
|--------|-----|-----------|
| Direction | Server → Client | Bidirectional |
| Protocol | Plain HTTP | Separate WS protocol |
| Reconnect | Automatic | Manual implementation |
| Proxy/firewall | Works everywhere | Sometimes blocked |
| Complexity | ~30 lines | ~100+ lines |

SSE fits perfectly: server pushes updates, client just listens.

---

## Event Types

| Event | Trigger | Payload |
|-------|---------|---------|
| `progress_update` | qBit poller | `{request_id, progress, eta}` |
| `state_change` | Any webhook | `{request_id, old_state, new_state}` |
| `request_created` | Jellyseerr webhook | `{request_id, title, poster_url}` |
| `request_deleted` | Delete action | `{request_id}` |

---

## Implementation

### 1. Backend: SSE Endpoint

**File:** `app/routers/events.py`

```python
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
import asyncio
import json

router = APIRouter(tags=["events"])

# Shared subscriber list
subscribers: list[asyncio.Queue] = []


@router.get("/events")
async def sse_endpoint():
    """SSE endpoint - browsers connect here for live updates."""
    queue = asyncio.Queue()
    subscribers.append(queue)

    async def event_stream():
        try:
            # Send initial heartbeat
            yield f"data: {json.dumps({'type': 'connected'})}\n\n"

            while True:
                data = await queue.get()
                yield f"data: {json.dumps(data)}\n\n"
        finally:
            subscribers.remove(queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # Disable nginx buffering
        }
    )


async def broadcast(event: dict):
    """Push event to all connected clients."""
    for queue in subscribers:
        await queue.put(event)
```

### 2. Backend: Broadcast Helper

**File:** `app/core/broadcaster.py` (update existing)

```python
from app.routers.events import broadcast

class Broadcaster:
    async def progress_update(self, request_id: int, progress: int, eta: int = -1):
        await broadcast({
            "type": "progress_update",
            "request_id": request_id,
            "progress": progress,
            "eta": eta,
        })

    async def state_change(self, request_id: int, old_state: str, new_state: str):
        await broadcast({
            "type": "state_change",
            "request_id": request_id,
            "old_state": old_state,
            "new_state": new_state,
        })

    async def request_created(self, request):
        await broadcast({
            "type": "request_created",
            "request_id": request.id,
            "title": request.title,
            "poster_url": request.poster_url,
            "state": request.state.value,
        })

broadcaster = Broadcaster()
```

### 3. Backend: qBit Poller Integration

**File:** `app/services/qbit_poller.py` (update)

```python
from app.core.broadcaster import broadcaster

PROGRESS_THRESHOLD = 2  # Only broadcast if changed by 2%+

async def update_download_progress(db, torrents):
    for torrent in torrents:
        request = await correlator.find_active_by_hash(db, torrent["hash"])
        if not request:
            continue

        old_progress = request.download_progress or 0
        new_progress = int(torrent["progress"] * 100)

        # Only broadcast significant changes
        if abs(new_progress - old_progress) >= PROGRESS_THRESHOLD:
            request.download_progress = new_progress
            await db.commit()

            await broadcaster.progress_update(
                request_id=request.id,
                progress=new_progress,
                eta=torrent.get("eta", -1),
            )
```

### 4. Frontend: EventSource Connection

```javascript
class LiveUpdates {
    constructor() {
        this.eventSource = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
    }

    connect() {
        this.eventSource = new EventSource('/events');

        this.eventSource.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.handleEvent(data);
        };

        this.eventSource.onopen = () => {
            console.log('SSE connected');
            this.reconnectAttempts = 0;
        };

        this.eventSource.onerror = () => {
            // EventSource auto-reconnects, but track attempts
            this.reconnectAttempts++;
            if (this.reconnectAttempts > this.maxReconnectAttempts) {
                console.error('SSE max reconnect attempts reached');
                this.eventSource.close();
            }
        };
    }

    handleEvent(data) {
        switch (data.type) {
            case 'progress_update':
                this.updateProgress(data.request_id, data.progress);
                break;
            case 'state_change':
                this.updateState(data.request_id, data.new_state);
                break;
            case 'request_created':
                this.addRequestCard(data);
                break;
            case 'request_deleted':
                this.removeRequestCard(data.request_id);
                break;
        }
    }

    updateProgress(requestId, progress) {
        const card = document.querySelector(`[data-request-id="${requestId}"]`);
        if (card) {
            const progressBar = card.querySelector('.progress-bar');
            const progressText = card.querySelector('.progress-text');
            if (progressBar) progressBar.style.width = `${progress}%`;
            if (progressText) progressText.textContent = `${progress}%`;
        }
    }

    updateState(requestId, newState) {
        const card = document.querySelector(`[data-request-id="${requestId}"]`);
        if (card) {
            const stateEl = card.querySelector('.state');
            if (stateEl) {
                stateEl.textContent = newState;
                stateEl.className = `state state-${newState.toLowerCase()}`;
            }
        }
    }

    // ... addRequestCard, removeRequestCard implementations
}

// Initialize on page load
document.addEventListener('DOMContentLoaded', () => {
    const liveUpdates = new LiveUpdates();
    liveUpdates.connect();
});
```

---

## Register Router

**File:** `app/main.py`

```python
from app.routers import events

app.include_router(events.router)
```

---

## Deployment Considerations

### Nginx (if used)

Disable buffering for SSE endpoint:

```nginx
location /events {
    proxy_pass http://backend:8000;
    proxy_buffering off;
    proxy_cache off;
    proxy_set_header Connection '';
    proxy_http_version 1.1;
    chunked_transfer_encoding off;
}
```

### Multiple Workers

If running multiple backend workers (uvicorn with `--workers`), each worker has its own subscriber list. Options:

1. **Single worker** - Simplest, fine for low traffic
2. **Redis pub/sub** - Workers publish to Redis, Redis fans out to subscribers
3. **Broadcast via DB** - Poll DB for changes (defeats purpose)

Recommend: Start with single worker, add Redis later if needed.

---

## Testing

```bash
# Terminal 1: Watch SSE stream
curl -N http://localhost:8000/events

# Terminal 2: Trigger a progress update (via API or webhook)
# You should see events appear in Terminal 1
```

---

## Files to Create/Modify

| File | Action |
|------|--------|
| `app/routers/events.py` | Create - SSE endpoint |
| `app/core/broadcaster.py` | Update - Add broadcast methods |
| `app/services/qbit_poller.py` | Update - Call broadcaster |
| `app/main.py` | Update - Register router |
| `frontend/js/live-updates.js` | Create - EventSource client |

---

## Dependencies

None - SSE uses standard HTTP, EventSource is built into all browsers.

---

## Estimated Effort

- Backend: ~1 hour
- Frontend: ~1-2 hours (depends on current structure)
- Testing: ~30 min

Total: Half day
