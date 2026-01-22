# Bug: SSE Connections Dropping After 1-2 Seconds

**Created:** 2026-01-22
**Status:** Open (Fix implemented, awaiting test)
**Priority:** High
**Component:** SSE / Real-time Updates

## Problem

SSE clients disconnect after 1-2 seconds of connection. This causes the UI to show stale data (e.g., 0% progress when actual download is at 31%).

## Symptoms

- UI shows "Live updates active" (green dot)
- Connection drops within 1-2 seconds
- Client reconnects immediately
- Cycle repeats indefinitely
- UI shows stale data between reconnections

## Evidence

Server logs show rapid connect/disconnect pattern:

```
04:29:57 - Client connected (1 client)
04:29:58 - Client disconnected (0 clients)  # 1 second later
04:29:58 - Client connected (1 client)
04:30:00 - Client disconnected (0 clients)  # 2 seconds later
```

Database has correct data (verified via API):
- Progress: 31%
- Speed: 55.9 MB/s
- qBit polling IS working

## Distinction from Other SSE Issues

This is **NOT** the same as:
- `detail-page-live-updates-bug.md` - That's about events not arriving (connection stable)
- `2026-01-22-sse-not-pushing-updates.md` - That's about broadcast timing (connection stable)

This issue is specifically about **connections being terminated** by something.

## Possible Causes

1. **Missing keepalive/heartbeat** - No periodic ping to maintain connection
2. **Proxy/reverse proxy timeout** - nginx/traefik closing idle connections
3. **Browser timeout** - EventSource default timeout
4. **Error in SSE generator** - Exception causing early termination
5. **Docker networking** - Container network timeout

## Files to Investigate

| File | Purpose |
|------|---------|
| `app/routers/sse.py` | SSE endpoint, event generator |
| `app/core/broadcaster.py` | Client management, subscriptions |
| Docker/nginx configs | Proxy timeout settings |

## Debug Plan

1. Add logging to SSE generator to see why it exits
2. Check if keepalive messages are being sent
3. Check browser Network tab for SSE stream closure reason
4. Review proxy timeout settings

## Potential Fixes

1. **Add heartbeat**: Send periodic `:keepalive` comments to maintain connection
2. **Increase timeouts**: Configure nginx/proxy with longer SSE timeouts
3. **Error handling**: Wrap generator in try/except to log exceptions

## Fix Implementation (2026-01-22)

**Root Cause Identified:** No heartbeat mechanism between messages. The `subscribe()` method waited indefinitely on `queue.get()`, leaving the connection completely idle. Proxies/browsers timeout idle connections after a few seconds.

**Fix Applied:** Added periodic heartbeat in `app/core/broadcaster.py`

```python
# New constant
SSE_HEARTBEAT_INTERVAL = 15  # seconds

# Updated subscribe() method
async def subscribe(self) -> AsyncGenerator[str, None]:
    # ... setup ...
    try:
        while True:
            try:
                # Wait for message with timeout for heartbeat
                data = await asyncio.wait_for(
                    queue.get(), timeout=SSE_HEARTBEAT_INTERVAL
                )
                yield data
            except asyncio.TimeoutError:
                # Send SSE comment (ignored by clients, keeps connection alive)
                yield ": heartbeat\n\n"
                logger.debug("Sent SSE heartbeat")
    # ... cleanup ...
```

**How It Works:**
- Uses `asyncio.wait_for()` with 15-second timeout instead of indefinite wait
- On timeout, sends SSE comment (`: heartbeat\n\n`) which browsers ignore but keeps TCP connection alive
- Logs heartbeat at DEBUG level for monitoring

**Testing Required:**
- [ ] Deploy to dev server
- [ ] Open dashboard and monitor SSE connection stability
- [ ] Verify connections stay open longer than 15 seconds
- [ ] Check logs for "Sent SSE heartbeat" messages
- [ ] Verify UI updates in real-time during active downloads

## Related

- `issues/detail-page-live-updates-bug.md` - General live update issue
- Plan file: `/home/adept/.claude/plans/mossy-waddling-sketch.md` - Debug approach
