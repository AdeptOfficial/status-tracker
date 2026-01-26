# Issue: qBittorrent Progress Only Broadcasts on 5% Changes

**Date:** 2026-01-25
**Severity:** Low (UX issue)
**Status:** RESOLVED
**Type:** Code fix

---

## Problem

Download progress on the dashboard doesn't update in real-time. Progress appears stuck at 0.0% while qBittorrent shows active downloading (e.g., 2.8%).

## Root Cause

`app/plugins/qbittorrent.py` only broadcasts progress updates when there's a 5% change threshold:

```python
# Lines ~325-330
if abs(new_progress - old_progress) >= 0.05:  # 5% threshold
    await broadcaster.broadcast_update(request)
```

This means:
- User sees 0.0% → 5.0% → 10.0% jumps
- Small/fast downloads may complete before first update
- UI feels "stuck" during initial download phase

## Expected Behavior

Progress should update continuously (or with much smaller threshold like 0.5%) for better UX.

## Proposed Fix

Option A: Remove threshold entirely
```python
# Broadcast on every poll
await broadcaster.broadcast_update(request)
```

Option B: Reduce threshold significantly
```python
if abs(new_progress - old_progress) >= 0.005:  # 0.5% threshold
    await broadcaster.broadcast_update(request)
```

Option C: Time-based broadcast (every N seconds regardless of progress change)

## Trade-offs

- **More broadcasts** = More SSE traffic, but minimal impact for single-user dashboard
- **No threshold** = Smooth UX but potentially unnecessary updates for stalled downloads

## Files to Modify

- `app/plugins/qbittorrent.py` (lines ~325-330)

## Testing

1. Request new content
2. Watch dashboard during download
3. Verify progress updates smoothly (not in 5% jumps)

## Resolution

Applied **Option A** - Always return `True` for progress updates in DOWNLOADING state. The 5% threshold is kept only for debug logging (to reduce log spam).

```python
# Log significant progress changes (5% threshold to reduce log spam)
if abs(progress - old_progress) >= 0.05:
    logger.debug(
        f"Download progress: {request.title} - "
        f"{progress * 100:.1f}% ({request.download_speed})"
    )

# Always broadcast progress updates for smooth UX
# The 3s poll interval already throttles updates adequately
return True
```

**Why this approach:**
- Poll interval (3s) already provides natural throttling
- Single-user dashboard can handle frequent SSE updates
- Smooth UX is more important than minimal network overhead

## Notes

Discovered during 2026-01-25 debug session. User explicitly requested: "broadcast all progress changes - note this down, no code change until we finish the test flow."
