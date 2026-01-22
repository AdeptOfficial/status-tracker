# Session Handoff: Per-Episode Tracking + Polling Speed

**Date:** 2026-01-22
**Session:** Per-Episode UI + qBit Polling + Lycoris VFS Investigation
**Branch:** `feature/per-episode-tracking`
**Status:** Code deployed, Lycoris Recoil stuck due to Shokofin VFS issue

---

## What Was Accomplished This Session

### 1. Committed Previous Session's Changes ✅

Pushed to `fix/media-workflow-audit`:
- VFS refresh in fallback checker
- SSE fix (sse:refresh → status-update)
- Diagnostic logging
- IMPORTING state skipped issue

### 2. Created New Feature Branch ✅

Branch: `feature/per-episode-tracking` (based on `fix/media-workflow-audit`)

### 3. Implemented Per-Episode Tracking UI ✅

**Schema changes** (`app/schemas.py`):
- Created `EpisodeResponse` schema (moved up for forward reference)
- Created `MediaRequestWithEpisodesResponse` extending `MediaRequestResponse` with `episodes: list[EpisodeResponse]`
- Updated `MediaRequestDetailResponse` to extend `MediaRequestWithEpisodesResponse`
- Updated `RequestListResponse` to use `MediaRequestWithEpisodesResponse`

**API changes** (`app/routers/api.py`, `app/routers/pages.py`):
- Added `selectinload(MediaRequest.episodes)` to all request queries
- Updated response types to use `MediaRequestWithEpisodesResponse`

**UI changes** (`app/templates/components/card.html`):
- Added episode progress bar (green=available, cyan=downloading)
- Added episode count summary ("3/13 ready")
- Added expandable `<details>` element with per-episode list
- Episode states shown with icons: ✓ (available), ⬇ (downloading), ○ (pending), etc.

**UI changes** (`app/templates/detail.html`):
- Added "Episode Progress" section with visual progress bar
- Color-coded legend (green=ready, orange=processing, cyan=downloading, gray=pending)
- Full episode list with state badges

### 4. Increased qBittorrent Polling Speed ✅

**File:** `app/plugins/qbittorrent.py`

| Setting | Before | After |
|---------|--------|-------|
| POLL_FAST | 5s | 3s |
| POLL_SLOW | 30s | 15s |

### 5. Deployed to Dev Server ✅

All changes deployed to LXC 220 (media-dev).

---

## What Still Needs To Be Done

### 1. Lycoris Recoil Stuck at ANIME_MATCHING ❌

**Problem:** Lycoris Recoil (TV anime, 13 episodes) stuck at `anime_matching` state.

**Investigation findings:**
- Files ARE in correct location: `/data/anime/shows/Lycoris Recoil/` (13 mkv files)
- Shoko HAS matched the series (logs show "Saving Series Lycoris Recoil")
- Shoko queue is empty (processing complete)
- Shokofin SignalR connected to Shoko (since 02:41:58)
- VFS regeneration creates **0 new entries** for Lycoris Recoil
- VFS only contains SNAFU (2 series, 13 episodes total)

**Root cause:** Shokofin VFS not including Lycoris Recoil despite Shoko having it matched. This is a Shoko↔Shokofin sync issue, NOT a status-tracker issue.

**Next step:** Check Shoko web UI → Import Folders → verify Lycoris Recoil files are linked to the correct import folder (anime_shows, ID=1).

### 2. Commit Per-Episode Changes ❌

Changes are deployed but NOT committed to git yet:
```bash
cd /home/adept/git/status-tracker-workflow-fix
git add -A && git commit -m "Add per-episode tracking UI, increase polling speed" && git push
```

### 3. Test Per-Episode UI ❌

Once Lycoris Recoil becomes available, verify:
- Dashboard shows episode progress bar
- Dashboard shows expandable episode list
- Detail page shows full episode breakdown

---

## Key Architecture

### Media Flow
```
Jellyseerr → Radarr/Sonarr → qBittorrent → Shoko (anime) → Jellyfin
```

### States
```
REQUESTED → APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE
                                                      ↓ (anime)
                                               ANIME_MATCHING
                                                      ↓
                                                 AVAILABLE
```

### Episode Model
- Created at Sonarr Grab time from `episodes[]` array
- States: GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING/ANIME_MATCHING → AVAILABLE
- Season packs: all episodes share same `qbit_hash`

---

## Key Files Reference

| Purpose | File |
|---------|------|
| State machine | `app/core/state_machine.py` |
| SSE broadcaster | `app/core/broadcaster.py` |
| Fallback checker | `app/services/jellyfin_verifier.py` |
| qBit polling config | `app/plugins/qbittorrent.py` (POLL_FAST=3, POLL_SLOW=15) |
| Episode model | `app/models.py:299` |
| API schemas | `app/schemas.py` |
| Card template | `app/templates/components/card.html` |
| Detail template | `app/templates/detail.html` |

---

## VFS Troubleshooting Reference

### Check VFS contents
```bash
ssh root@10.0.2.10 "pct exec 220 -- docker exec jellyfin ls -la '/config/Shokofin/VFS/29391378-c411-8b35-b77f-84980d25f0a6/'"
```

### Library IDs
| Library | VFS Path |
|---------|----------|
| Anime Shows | `29391378-c411-8b35-b77f-84980d25f0a6` |
| Anime Movies | `abebc196-cc1b-8bbf-6f8b-b5ca7b5ad6f1` |
| TV-Shows | `3e840160-b2d8-a553-d882-13a62925f0fa` (MISSING - not configured) |

### Check Shoko series
```bash
ssh root@10.0.2.10 "pct exec 220 -- docker logs shoko --tail 50 2>&1" | grep -i 'lycoris'
```

### Check Shokofin SignalR
```bash
ssh root@10.0.2.10 "pct exec 220 -- docker logs jellyfin 2>&1" | grep -i 'signalr.*connected'
```

### Check fallback checker
```bash
ssh root@10.0.2.10 "pct exec 220 -- docker logs status-tracker --tail 50" | grep -i 'FALLBACK'
```

---

## Deploy Commands

```bash
# Sync to dev (ALWAYS exclude .env!)
rsync -avz --exclude '.env' --exclude '__pycache__' --exclude '.git' \
  /home/adept/git/status-tracker-workflow-fix/ root@10.0.2.10:/tmp/status-tracker-update/

# Copy into LXC 220 (preserves server .env)
ssh root@10.0.2.10 "cd /tmp/status-tracker-update && tar --exclude='.env' -cf - . | pct exec 220 -- tar -xf - -C /opt/status-tracker/"

# Rebuild container
ssh root@10.0.2.10 "pct exec 220 -- bash -c 'cd /opt/status-tracker && docker compose up -d --build'"

# Check health
ssh root@10.0.2.10 "pct exec 220 -- curl -s http://localhost:8100/api/health"

# Tail logs
ssh root@10.0.2.10 "pct exec 220 -- docker logs status-tracker --tail 50"
```

---

## Security Protocols (CRITICAL)

- **NEVER** read `.env` files, `config.xml`, `settings.json`
- **NEVER** run `printenv`, `env`, `docker inspect`, `docker-compose config`
- **ALWAYS** exclude `.env` when syncing/deploying
- If credentials appear, **STOP** and notify user

---

## Current Requests on Dev

| ID | Title | State | Type | Notes |
|----|-------|-------|------|-------|
| 6 | Lycoris Recoil | anime_matching | TV/Anime | Stuck - Shokofin VFS issue |
| 5 | Rascal Does Not Dream... | available | Movie/Anime | Working |
| 4 | Your Name. | available | Movie/Anime | Working |
| 2 | SNAFU | available | TV/Anime | Working |
| 3 | Akira | available | Movie/Anime | Working |

---

## Git Status

Branch: `feature/per-episode-tracking`
Last commit: `7c6ffa5` - "Increase qBittorrent polling frequency"

**Uncommitted but deployed:**
- Per-episode tracking UI (schemas, API, templates)

---

## Roadmap (from DIARY.md)

| Priority | Task |
|----------|------|
| 1 | Fix Lycoris Recoil (Shokofin VFS issue) |
| 2 | Commit per-episode changes |
| 3 | Test per-episode UI with working TV show |
| 4 | Fix IMPORTING state skipped for anime |
