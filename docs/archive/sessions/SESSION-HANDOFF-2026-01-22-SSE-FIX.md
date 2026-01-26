# Session Handoff: SSE Fix & Fallback Checker Enhancement

**Date:** 2026-01-22
**Session:** SSE Live Updates Fix + VFS Refresh Feature
**Status:** Partially complete - needs commit and per-episode UI work

---

## What Was Accomplished This Session

### 1. Fixed SSE Live Updates Not Pushing to Frontend ✅

**Problem:** Dashboard showed "Live updates active" but UI never updated without manual refresh.

**Root Cause:** htmx reserves `sse:` prefix for its SSE extension. Using `hx-trigger="sse:refresh"` caused `htmx:noSSESourceError`.

**Fix:** Renamed custom event from `sse:refresh` → `status-update`

**Files changed:**
- `app/templates/index.html` - lines 24, 115
- `app/templates/detail.html` - lines 52, 406

**Verified working:** Real-time updates now work (tested with "Rascal Does Not Dream of a Dreaming Girl")

### 2. Added Diagnostic Logging to Broadcaster ✅

**Files changed:**
- `app/core/broadcaster.py` - Added logging for client count and broadcast calls
- `app/routers/sse.py` - Added debug logging for SSE event yields

### 3. Enhanced Fallback Checker with Library Refresh ✅

**Problem:** Anime stuck at `ANIME_MATCHING` because Shokofin VFS doesn't regenerate automatically.

**Fix:** Fallback checker now triggers Jellyfin library scan for stuck `ANIME_MATCHING` requests, forcing Shokofin VFS regeneration.

**File changed:** `app/services/jellyfin_verifier.py` (lines ~439-449)

```python
# Now triggers scan for ANIME_MATCHING to force Shokofin VFS regeneration
if anime_matching_requests or importing_requests:
    logger.info(f"[FALLBACK] Triggering Jellyfin library scan...")
    await jellyfin_client.trigger_library_scan()
    await asyncio.sleep(3)  # Let VFS regenerate
```

**Verified working:** "Rascal Does Not Dream of a Dreaming Girl" transitioned from `anime_matching` → `available` automatically.

### 4. Created Issue for IMPORTING State Skipped ✅

**Problem:** Anime goes `DOWNLOADED → ANIME_MATCHING`, skipping `IMPORTING` state.

**Issue created:** `docs/issues/2026-01-22-importing-state-skipped-for-anime.md`

**Added to roadmap:** Priority 1 in DIARY.md

---

## What Still Needs To Be Done

### 1. Commit Changes to Feature Branch (PENDING)

Changes ready but NOT committed:
```
modified:   DIARY.md
modified:   app/core/broadcaster.py
modified:   app/routers/sse.py
modified:   app/services/jellyfin_verifier.py
modified:   app/templates/detail.html
modified:   app/templates/index.html
new file:   docs/issues/2026-01-22-importing-state-skipped-for-anime.md
renamed:    docs/issues/2026-01-22-sse-not-pushing-updates.md -> resolved/
```

### 2. Per-Episode Monitoring (DISCOVERED GAP)

**Current state:**
- Episode model EXISTS in `app/models.py`
- Episodes ARE created on Sonarr grab (see `app/plugins/sonarr.py`)
- EpisodeResponse schema EXISTS
- Separate `/requests/{id}/episodes` endpoint EXISTS

**Missing:**
- Episodes NOT included in main `/api/requests` response
- UI does NOT display per-episode progress
- Need to add `episodes: list[EpisodeResponse]` to `MediaRequestResponse`

**Issue file:** `issues/per-episode-download-tracking.md`

### 3. Test Lycoris Recoil (TV Show)

Currently at `approved` state - waiting for Sonarr to grab. Good test for per-episode tracking once implemented.

---

## Key Files Reference

| Purpose | File |
|---------|------|
| State machine | `app/core/state_machine.py` |
| SSE broadcaster | `app/core/broadcaster.py` |
| Fallback checker | `app/services/jellyfin_verifier.py` |
| Sonarr plugin (episodes) | `app/plugins/sonarr.py` |
| Episode model | `app/models.py:299` |
| API schemas | `app/schemas.py` |
| Main templates | `app/templates/index.html`, `detail.html` |
| MVP requirements | `docs/MVP.md` |
| Roadmap | `DIARY.md` |

---

## Current Request States (Dev Server)

| ID | Title | State | Type |
|----|-------|-------|------|
| 6 | Lycoris Recoil | approved | TV/Anime |
| 5 | Rascal Does Not Dream... | available | Movie/Anime |
| 4 | Your Name. | available | Movie/Anime |
| 2 | My Teen Romantic Comedy SNAFU | available | TV/Anime |
| 3 | Akira | available | Movie/Anime |

---

## Deployment Info

- **Dev server:** `ssh root@10.0.2.10`
- **LXC:** 220 (media-dev, 10.0.2.20)
- **Status-tracker port:** 8100
- **Feature branch:** `fix/media-workflow-audit`
- **Deploy command:**
  ```bash
  rsync -avz --exclude '.env' --exclude '__pycache__' /home/adept/git/status-tracker-workflow-fix/ root@10.0.2.10:/tmp/status-tracker-update/
  ssh root@10.0.2.10 "cd /tmp/status-tracker-update && tar --exclude='.env' -cf - . | pct exec 220 -- tar -xf - -C /opt/status-tracker/"
  ssh root@10.0.2.10 "pct exec 220 -- bash -c 'cd /opt/status-tracker && docker compose up -d --build'"
  ```

---

## Security Protocols (CRITICAL)

- NEVER read `.env` files
- NEVER run `printenv`, `env`, `docker inspect`, `docker-compose config`
- NEVER expose API keys or credentials
- Always exclude `.env` when syncing code
- If you see credentials, STOP and notify user

---

## Git Status

Branch: `fix/media-workflow-audit`
Last commit: `3eeb52b` - "Fix SSE live updates not pushing to frontend"

**Uncommitted changes:**
- Fallback checker VFS refresh enhancement
- IMPORTING state skipped issue
- DIARY.md roadmap updates
