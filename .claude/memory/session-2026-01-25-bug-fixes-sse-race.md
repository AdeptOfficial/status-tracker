# Session Memory: Status-Tracker Bug Fixes (SSE, Race Condition, Timeline)

**Date:** 2026-01-25
**Status:** Deployed and Ready to Monitor

---

## Context

Continued from previous session. Deployed fixes for 3 bugs found during anime movie testing with "Summer Ghost" (2021).

## Security Protocols (CRITICAL)

From `/home/adept/git/homeserver/CLAUDE.md`:
- **NEVER** read `.env`, `config.xml`, `settings.json` without explicit request
- **NEVER** run `printenv`, `env`, `docker inspect`, `docker-compose config`
- **NEVER** SSH into servers unless user explicitly asks
- **NEVER** display or leak API keys
- If credentials found: STOP, notify user, create issue

## Dev Environment

- **Proxmox host:** 10.0.2.10
- **Media-dev LXC:** 10.0.2.20 (VMID 220)
- **Status-Tracker:** http://10.0.2.20:8100
- **Deploy script:** `/home/adept/git/status-tracker-workflow-fix/scripts/deploy.sh`
- **Database:** `/config/tracker.db` (inside container)

---

## Bugs Fixed This Session

### 1. Timeline "fetching metadata..." Never Updates ✅ DEPLOYED

**File:** `app/plugins/qbittorrent.py`

**Problem:** When transitioning to DOWNLOADING during `metaDL` state, size is 0. Timeline showed "Downloading: fetching metadata..." which never updated.

**Fix:** Changed timeline entry to show "Download started" instead. Size is shown in DOWNLOADED entry where it's accurate.

**Code change (lines 283-298):**
```python
# Before:
if torrent.size and torrent.size > 0:
    size_text = format_size(torrent.size)
else:
    size_text = "fetching metadata..."
details=f"Downloading: {size_text}"

# After:
details="Download started"
```

### 2. Race Condition: Radarr Import Before qBit Complete ✅ DEPLOYED

**File:** `app/plugins/radarr.py`

**Problem:** Radarr import event arrives ~1 second before qBit complete event. State machine rejects DOWNLOADING → ANIME_MATCHING transition. Fallback handles it after ~2 min delay.

**Fix:** When Radarr import arrives during DOWNLOADING state:
1. Check qBit API to confirm download is complete
2. Transition to DOWNLOADED first (preserves state flow)
3. Then proceed with import transition

**New methods added:**
- `_ensure_downloaded_state()` - Checks qBit when import arrives during DOWNLOADING
- `_force_downloaded_transition()` - Transitions to DOWNLOADED with proper timeline entry

**Flow preserved:**
```
DOWNLOADING → DOWNLOADED → IMPORTING → ANIME_MATCHING → AVAILABLE
     ↑            ↑
  qBit check   Radarr import
```

### 3. SSE Disconnection Issues ✅ DEPLOYED

**Files changed:**
- `app/templates/base.html` - Removed unused htmx SSE extension
- `app/core/broadcaster.py` - Refactored to yield dicts instead of raw SSE strings
- `app/routers/sse.py` - Simplified dict-based communication
- `app/templates/index.html` - Improved reconnection logic
- `app/templates/detail.html` - Same frontend improvements

**Problems fixed:**
1. Double conversion (string→dict→string) caused parsing issues with heartbeats
2. No guard against duplicate connection attempts
3. Basic exponential backoff without jitter

**Key changes:**

**broadcaster.py:**
- `subscribe()` now yields `Optional[dict]` instead of raw SSE strings
- Yields `None` for heartbeats (SSE endpoint handles)
- `broadcast()` puts dict `{"event": event_type, "data": data}` in queue

**sse.py:**
- Yields `{"comment": "heartbeat"}` for None messages
- Clean dict handling: `{"event": name, "data": json.dumps(data)}`

**Frontend (index.html, detail.html):**
- Added `isConnecting` guard to prevent duplicate connections
- Exponential backoff with jitter: `delay * 1.5^attempts + random(0-1000)ms`
- Max reconnect attempts: 10 (was 5)
- Better error handling (checks `readyState`)

---

## Other Bugs Found (NOT Fixed This Session)

### Shoko Treats Movies as Series
- Summer Ghost identified as series with episode "Complete Movie"
- Sends `EpisodeUpdated` events instead of `MovieUpdated`
- This is AniDB/Shoko behavior, not status-tracker issue

### Shokofin VFS Path Missing
- `/config/Shokofin/VFS/3e840160-b2d8-a553-d882-13a62925f0fa` doesn't exist
- Jellyfin can't find Summer Ghost because VFS symlinks not generated
- Infrastructure issue, not status-tracker

---

## Files Changed Summary

```
app/plugins/qbittorrent.py        # "Download started" instead of "fetching metadata..."
app/plugins/radarr.py             # Race condition fix - check qBit before import
app/core/broadcaster.py           # Refactored to yield dicts
app/routers/sse.py                # Simplified dict-based communication
app/templates/base.html           # Removed unused htmx SSE extension
app/templates/index.html          # Improved SSE reconnection logic
app/templates/detail.html         # Same frontend improvements
```

---

## Database Changes

**Summer Ghost (ID: 5):** Manually marked as AVAILABLE for testing
- State: AVAILABLE
- jellyfin_id: None (VFS issue prevents Jellyfin from seeing it)

---

## Current System Status

All services healthy after deploy:
- Uvicorn running on :8000
- 6 plugins loaded
- Shoko SignalR connected
- Polling loop started
- Jellyfin fallback checker started
- SSE clients connecting

---

## Resume Prompt

```
Continue status-tracker testing from session `.claude/memory/session-2026-01-25-bug-fixes-sse-race.md`

Working directory: /home/adept/git/status-tracker-workflow-fix

STATUS: All fixes deployed, ready to monitor

DEPLOYED FIXES:
1. Timeline "fetching metadata..." → now shows "Download started" (qbittorrent.py)
2. Race condition fixed → Radarr checks qBit before import transition (radarr.py)
3. SSE refactored → dict-based communication, improved reconnection (broadcaster.py, sse.py, templates)

SECURITY PROTOCOLS (CRITICAL):
- NEVER read .env, config.xml, settings.json without explicit request
- NEVER run printenv, env, docker inspect
- NEVER display or leak API keys
- NEVER SSH without explicit permission
- Dev server: 10.0.2.20:8100 (LXC 220)

KNOWN ISSUES (not status-tracker bugs):
- Shoko treats some movies as series (AniDB categorization)
- Shokofin VFS path missing for some content (infrastructure)

DATABASE NOTE: Summer Ghost (ID 5) manually marked AVAILABLE (no jellyfin_id due to VFS issue)

NEXT ACTION: Monitor a new anime movie request to verify all fixes work:
1. Timeline should show "Download started" (not "fetching metadata...")
2. State flow should be: DOWNLOADING → DOWNLOADED → ANIME_MATCHING (no race rejection)
3. SSE should stay connected without rapid disconnect/reconnect cycles

Deploy command if needed: cd /home/adept/git/status-tracker-workflow-fix && ./scripts/deploy.sh
```
