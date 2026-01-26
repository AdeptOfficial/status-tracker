# Issue: SSE Not Pushing Live Updates

**Date:** 2026-01-22
**Severity:** High
**Status:** Open

---

## Problem

Dashboard shows "Live updates active" (green indicator) but state changes don't push to the frontend. User must manually refresh to see updated state.

**Observed:**
- Backend state: `downloading` (confirmed via API)
- Frontend shows: `approved` (stale)
- SSE connection: Active (green dot visible)

## Timeline

1. Applied fix to move broadcasts after `db.commit()` in:
   - `main.py` polling loop
   - `jellyfin_verifier.py` fallback checker
   - `timeout_checker.py`

2. Deployed and restarted container

3. Tested with new request "My Teen Romantic Comedy SNAFU"
   - Request created → Approved (did this push?)
   - Sonarr grabbed → Grabbing (did NOT push)
   - qBit started → Downloading (did NOT push)

## Possible Causes

1. **Broadcasts not being called** - The broadcast_update() calls may not be executing
2. **No clients when broadcast happens** - SSE reconnects may cause timing issues
3. **Frontend not handling events** - JS event handler may be broken
4. **Wrong event format** - SSE message format may not match what frontend expects

## Debug Steps Needed

1. Add logging to `broadcaster.broadcast_update()` to confirm:
   - Method is called
   - Number of connected clients at broadcast time
   - Message being sent

2. Check browser dev tools Network tab for SSE messages

3. Check browser console for JS errors

## Files Involved

- `app/core/broadcaster.py` - SSE broadcast logic
- `app/routers/sse.py` - SSE endpoint
- `static/js/app.js` (or similar) - Frontend SSE handler

## Related

- Bug #12: SSE broadcasts before commit (partially fixed, but updates still not working)
