# Status Tracker: Detail Page Live Updates Not Working

**Created:** 2026-01-18
**Status:** Not reproduced in isolated browser acceptance (2026-10-17); real download pipeline verification pending
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

## 2026-10-17 browser acceptance evidence

Tested current source in real headless Firefox with a fresh profile, a temporary
SQLite database and one synthetic movie request. The fixture mounted the current
app read-only and used the real pages router, SSE router, broadcaster and HTMX
handler. Production background integrations were not started. HTMX 1.9.10 loaded
from the same CDN used by the app. No live requests, downloads or server data were
changed. This was a local browser test, not a deployed media-pipeline test.

Passed:
- SSE connected and the page displayed “Live updates active”.
- Server-side synthetic update changed progress from 10% to 55%, speed from
  1 MB/s to 5 MB/s and ETA from 10m to 2m without a page reload.
- A new timeline entry appeared through the same HTMX swap.
- Restarting only the fixture server disconnected the stream; the existing page
  reconnected and received a subsequent 85% update.
- Status changed to “Ready to Watch” without a manual refresh.
- A document marker survived updates and reconnection, establishing that the
  result was not caused by a full-page reload.

Final browser run passed. Two initial harness mistakes were corrected: speed/ETA
fixtures must use formatted strings, and the status assertion must account for
CSS uppercase text. Neither required an application change.

Local harness/evidence: `/tmp/status-tracker-browser-test/` (`fixture.py`,
`check.mjs`, `result.png`); temporary artifacts may be removed. Test container was
stopped after verification. The original end-to-end report is not fully closed:
real qBittorrent polling, proxy paths, and physical browser behavior were not
exercised. No application fix or deployment was needed for the tested path.

## 2026-10-17 dev pipeline observation attempt

Read-only checks used DEV `<media-dev>:8100` (LXC <media-dev>), not production.
`/api/requests/active` returned zero requests; no new download was started.
Health reports database connected, all six plugins loaded and Shoko SignalR
connected. Historical request 19 (regular movie) records approval, grab, download,
import and Jellyfin verification. Requests 18 (anime movie) and 17 (anime TV)
record anime matching followed by Jellyfin verification; all have a Jellyfin ID.
These events are dated January 26, 2026: historical evidence only, not a current
end-to-end test or current playback verification. Fresh real-service acceptance
remains pending an active dev request. Production was not accessed or changed.

## Triage 2026-10-20

**Verdict:** Not reproducible. **Status:** Resolved (triage, repo evidence; no live check in this pass).
Record already states "not reproduced in isolated browser acceptance"; Oct 20 roadmap entry lists live updates and reconnection as verified on DEV.
