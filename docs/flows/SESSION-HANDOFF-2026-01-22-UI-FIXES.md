# Session Handoff: UI Fixes + VFS Reliability

**Date:** 2026-01-22
**Session:** UI improvements, VFS fix, SSE debugging
**Branch:** `feature/per-episode-tracking`
**Status:** Multiple issues identified, some fixed, some documented

---

## What Was Accomplished This Session

### 1. Fixed Lycoris Recoil VFS Issue ✅

**Problem:** Lycoris Recoil stuck at `anime_matching` - Shokofin VFS not including it despite Shoko having it matched.

**Root cause:** VFS wasn't regenerated after Lycoris was added. SNAFU worked because VFS was generated when it was added.

**Fix:** Triggered Jellyfin library refresh via API:
```bash
curl -X POST 'http://jellyfin:8096/Library/Refresh' -H 'X-Emby-Token: API_KEY'
```

**Result:** VFS regenerated, Lycoris appeared, fallback checker marked it AVAILABLE with all 13 episodes.

### 2. Improved VFS Regeneration Reliability ✅

**File:** `app/services/jellyfin_verifier.py`

**Change:** Increased `VFS_REGENERATION_DELAY` from 3s to 10s after library scan trigger.

```python
VFS_REGENERATION_DELAY = 10  # seconds (increased from 3s for reliability)
```

**Committed:** `dec409a` - "Increase VFS regeneration delay for reliability"

### 3. Tested Per-Episode UI with Bocchi the Rock ✅

Requested "BOCCHI THE ROCK!" (12 episodes) to test flow:
- ✅ Jellyseerr webhook → APPROVED
- ✅ Sonarr grab → GRABBING (12 episodes created)
- ✅ qBit download → DOWNLOADING
- ✅ Per-episode tracking working (all 12 episodes shown)
- ✅ Quality: Bluray-1080p Remux from Nyaa.si

### 4. Created UI Improvement Issue ✅

**File:** `issues/ui-episode-progress-improvements.md`

**Captures these user requests:**
1. Timeline: "grabbing" → "Grabbed" (past tense)
2. Episode Progress: Show "x/12 downloaded, y/12 ready" (not just ready)
3. Remove "Matching" label for anime TV → show "Downloaded"
4. Per-episode download % (from MVP.md)
5. New SEARCHING state for Sonarr indexer searches

### 5. Identified SSE Live Update Bug ❌

**Problem:** UI shows 0% progress while actual download is at 31%.

**Investigation:**
- Database has correct progress (31%, 55.9 MB/s)
- Polling IS working
- SSE connections keep disconnecting after 1-2 seconds
- Rapid connect/disconnect pattern in logs

**Logs show:**
```
04:29:57 - Client connected (1 client)
04:29:58 - Client disconnected (0 clients)  # 1 second later!
04:29:58 - Client connected (1 client)
04:30:00 - Client disconnected (0 clients)  # 2 seconds later!
```

**Status:** Not fixed, needs investigation. Possible causes:
- Browser/proxy timeout
- Missing keepalive pings
- Error in SSE generator

---

## Known Bugs (Documented)

| Bug | Issue File | Status |
|-----|------------|--------|
| IMPORTING state skipped for anime | `docs/issues/2026-01-22-importing-state-skipped-for-anime.md` | Open |
| SSE connections dropping rapidly | Needs issue file | Open |
| UI not showing real-time progress | Related to SSE bug | Open |

---

## Git Status

**Branch:** `feature/per-episode-tracking`
**Latest commit:** `dec409a` - "Increase VFS regeneration delay for reliability"

**All changes committed and pushed.**

---

## Key Files Reference

| Purpose | File |
|---------|------|
| VFS delay fix | `app/services/jellyfin_verifier.py` (VFS_REGENERATION_DELAY=10) |
| SSE endpoint | `app/routers/sse.py` |
| Broadcaster | `app/core/broadcaster.py` |
| qBit polling | `app/plugins/qbittorrent.py` (POLL_FAST=3, POLL_SLOW=15) |
| UI issues | `issues/ui-episode-progress-improvements.md` |

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
```

---

## Security Protocols (CRITICAL)

- **NEVER** read `.env` files, `config.xml`, `settings.json`
- **NEVER** run `printenv`, `env`, `docker inspect`, `docker-compose config`
- **ALWAYS** exclude `.env` when syncing/deploying
- If credentials appear, **STOP** and notify user

---

## Current Test Request

**Bocchi the Rock (ID: 7):**
- State: DOWNLOADING
- Episodes: 12 (all downloading)
- Quality: Bluray-1080p Remux
- Size: ~63 GB
- Progress: Was at 31% when session ended

---

## Next Priorities

| Priority | Task |
|----------|------|
| 1 | Fix SSE disconnection bug (connections drop after 1-2s) |
| 2 | Implement UI improvements from `issues/ui-episode-progress-improvements.md` |
| 3 | Fix IMPORTING state skipped for anime |
| 4 | Monitor Bocchi download → verify full flow to AVAILABLE |

---

## Roadmap (from DIARY.md)

| Priority | Task |
|----------|------|
| 1 | Fix IMPORTING state skipped for anime |
| 2 | Test anime TV shows (Bocchi is a good test) |
| 3 | Media sync button |
| 4 | Fix delete integration |
