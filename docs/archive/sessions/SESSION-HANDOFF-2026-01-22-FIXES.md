# Session Handoff: Bug Fixes + Bocchi Test Complete

**Date:** 2026-01-22
**Session:** SSE heartbeat, UI fixes, Jellyseerr/Jellyfin episode handling
**Branch:** `feature/per-episode-tracking`
**Status:** Multiple fixes deployed, Bocchi test successful

---

## What Was Accomplished This Session

### 1. SSE Heartbeat Fix ✅

**Problem:** SSE connections dropping after 1-2 seconds, UI showing stale data.

**Root cause:** No keepalive between messages. Connection sat idle, proxies/browsers timed out.

**Fix:** Added 15-second heartbeat in `app/core/broadcaster.py`

```python
SSE_HEARTBEAT_INTERVAL = 15

async def subscribe(self):
    try:
        data = await asyncio.wait_for(queue.get(), timeout=SSE_HEARTBEAT_INTERVAL)
        yield data
    except asyncio.TimeoutError:
        yield ": heartbeat\n\n"  # SSE comment keeps connection alive
```

**Issue file:** `issues/sse-connections-dropping.md`

### 2. Timeline "Grabbed" Label Fix ✅

**Problem:** Timeline showed "grabbing" (lowercase, present tense) instead of "Grabbed" (past tense).

**Fix:** Added `'grabbing': 'Grabbed'` to `state_labels` and `state_colors` in:
- `app/templates/detail.html`
- `app/templates/components/card.html`

### 3. /history 500 Error Fix ✅

**Problem:** History page returned 500 Internal Server Error (MissingGreenlet).

**Root cause:** Missing `selectinload(MediaRequest.episodes)` - card.html accessed episodes without eager loading.

**Fix:** Added selectinload to history query in `app/routers/pages.py`

**Issue file:** `issues/history-page-500-error.md`

### 4. Jellyseerr MEDIA_AVAILABLE Handler Fix ✅

**Problem:** When Jellyseerr sent MEDIA_AVAILABLE webhook:
- Episodes NOT marked as AVAILABLE (showed "Matching")
- `jellyfin_id` NOT set (no Watch button)

**Root cause:** Handler only transitioned request state, didn't update episodes or look up Jellyfin item.

**Fix:** Updated `app/plugins/jellyseerr.py`:
```python
if notification_type == "MEDIA_AVAILABLE":
    # Mark all episodes as available
    for episode in request.episodes:
        episode.state = EpisodeState.AVAILABLE

    # Look up Jellyfin item for Watch button
    jellyfin_item = await jellyfin_client.find_item_by_tvdb(...)
    if jellyfin_item:
        request.jellyfin_id = jellyfin_item.get("Id")
```

**Issue file:** `issues/jellyseerr-media-available-incomplete.md`

### 5. Jellyfin Plugin Episode Fix ✅

**Problem:** `jellyfin.py` ItemAdded webhook handler didn't mark episodes as AVAILABLE.

**Fix:** Added episode state update in `app/plugins/jellyfin.py`:
```python
for episode in request.episodes:
    episode.state = EpisodeState.AVAILABLE
```

### 6. Bocchi the Rock Test ✅

**Full flow completed successfully:**
- APPROVED (10:20) → GRABBING (10:23) → DOWNLOADING (10:23) → DOWNLOADED (10:44) → ANIME_MATCHING (10:45) → AVAILABLE (10:50)
- 12 episodes, 63GB Bluray Remux
- VFS regenerated automatically (Shokofin handled it)
- Jellyseerr MEDIA_AVAILABLE webhook triggered final transition

**Issue discovered:** Bocchi's episodes stuck at "Matching" because old handler didn't update them. Fix deployed but won't retroactively update existing data.

---

## All Paths to AVAILABLE Now Fixed

| Path | jellyfin_id | Episodes | File |
|------|-------------|----------|------|
| Fallback checker | ✅ | ✅ | `jellyfin_verifier.py` |
| Jellyseerr webhook | ✅ | ✅ | `jellyseerr.py` (FIXED) |
| Jellyfin webhook | ✅ | ✅ | `jellyfin.py` (FIXED) |
| Library sync | ✅ | N/A | `library_sync.py` |

---

## Known Bugs Still Open

| Bug | Issue File | Status |
|-----|------------|--------|
| IMPORTING state skipped for anime | `docs/issues/2026-01-22-importing-state-skipped-for-anime.md` | Open |
| Episode progress "0/12 ready" display | `issues/ui-episode-progress-improvements.md` | Open (UI only shows "ready", not "downloaded") |
| Bocchi episodes stuck at Matching | N/A | Existing data issue, new requests will work |

---

## UI Improvements Requested (Not Implemented Yet)

From `issues/ui-episode-progress-improvements.md`:
1. ~~Timeline: "grabbing" → "Grabbed"~~ ✅ DONE
2. Episode Progress: Show "x downloaded, y ready" (not just "x ready")
3. Per-episode download %
4. Remove "Matching" label for anime TV → show "Downloaded"
5. New SEARCHING state for Sonarr indexer searches

---

## Files Modified This Session

| File | Change |
|------|--------|
| `app/core/broadcaster.py` | SSE heartbeat (15s keepalive) |
| `app/routers/pages.py` | /history selectinload fix |
| `app/templates/detail.html` | Grabbed label + grabbing color |
| `app/templates/components/card.html` | Grabbed label + grabbing color |
| `app/plugins/jellyseerr.py` | MEDIA_AVAILABLE: episodes + jellyfin_id |
| `app/plugins/jellyfin.py` | ItemAdded: mark episodes AVAILABLE |

---

## Deploy Commands

```bash
# Sync to dev (ALWAYS exclude .env!)
rsync -avz --exclude '.env' --exclude '__pycache__' --exclude '.git' \
  /home/adept/git/status-tracker-workflow-fix/ root@10.0.2.10:/tmp/status-tracker-update/

# Copy into LXC 220
ssh root@10.0.2.10 "cd /tmp/status-tracker-update && tar --exclude='.env' -cf - . | pct exec 220 -- tar -xf - -C /opt/status-tracker/"

# Rebuild container
ssh root@10.0.2.10 "pct exec 220 -- bash -c 'cd /opt/status-tracker && docker compose up -d --build'"

# Check health
ssh root@10.0.2.10 "pct exec 220 -- curl -s http://localhost:8100/api/health"
```

---

## Security Protocols (CRITICAL)

- **NEVER** read `.env` files, `config.xml`, `settings.json`
- **NEVER** run `printenv`, `env`, `docker inspect`, `docker-compose config`
- **ALWAYS** exclude `.env` when syncing/deploying
- If credentials appear, **STOP** and notify user

---

## Current Requests on Dev

| ID | Title | State | Episodes | Notes |
|----|-------|-------|----------|-------|
| 7 | BOCCHI THE ROCK! | available | 0/12 ready | Episodes stuck at Matching (pre-fix) |
| 6 | Lycoris Recoil | available | 13/13 ready | Working correctly |
| 5 | Rascal Dreams... | available | Movie | Working |
| 4 | Your Name. | available | Movie | Working |
| 2 | SNAFU | available | 13/13 ready | Working |
| 3 | Akira | available | Movie | Working |

---

## Next Priorities

| Priority | Task |
|----------|------|
| 1 | Fix Bocchi's episode data (manual DB update or re-request) |
| 2 | Test SSE heartbeat stability |
| 3 | Implement remaining UI improvements |
| 4 | Fix IMPORTING state skipped for anime |
| 5 | Commit all changes to git |
