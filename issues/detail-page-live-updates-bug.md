# Status Tracker: Detail Page Live Updates Not Working

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker
**Priority:** High

## Problem

On the request detail page (`/request/{id}`), the "Live updates active" indicator shows as connected (green dot), but download progress does not update in real-time. Users must manually refresh the page to see progress changes.

### Observed Behavior
- SSE connection shows as "Live updates active" with green indicator
- Download percentage, speed, and ETA remain static
- Timeline events don't update
- Manual page refresh shows correct updated values

### Expected Behavior
- Download progress (percentage, speed, ETA) should update automatically every 5 seconds
- Timeline should update when new events occur
- No manual refresh needed

## Technical Context

The SSE endpoint (`/api/sse`) appears to be connected, but either:
1. Progress update events aren't being broadcast for the specific request
2. The detail page JavaScript isn't handling the events correctly
3. Events are filtered incorrectly on the detail page

### Relevant Files
- `app/routers/sse.py` - SSE endpoint
- `app/core/broadcaster.py` - Event broadcasting
- `app/plugins/qbittorrent.py` - Progress polling
- `app/templates/detail.html` - Detail page template

## Investigation Steps

1. Check if qBittorrent poller is broadcasting progress events
2. Verify event structure matches what detail.html expects
3. Check if detail page filters events by request ID correctly
4. Compare with index page SSE handling (which may work correctly)

## Acceptance Criteria

- [ ] Download progress updates in real-time on detail page
- [ ] Speed and ETA update without refresh
- [ ] Timeline events appear automatically
- [ ] SSE reconnection works after disconnect
