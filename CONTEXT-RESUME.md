# Status Tracker - Context Resume Prompt

**Last Updated:** 2026-01-22 (UI Fixes + SSE Bug Session)
**Branch:** `feature/per-episode-tracking`

---

## COPY EVERYTHING BELOW TO RESUME SESSION

---

I'm continuing work on the **status-tracker** app. Read these files for context:

1. `/home/adept/git/status-tracker-workflow-fix/docs/flows/SESSION-HANDOFF-2026-01-22-UI-FIXES.md`
2. `/home/adept/git/status-tracker-workflow-fix/DIARY.md`
3. `/home/adept/git/status-tracker-workflow-fix/issues/ui-episode-progress-improvements.md`

**Working directories:**
- App code: `/home/adept/git/status-tracker-workflow-fix/`
- Homeserver docs: `/home/adept/git/homeserver/`

---

## Current State Summary

### Completed ✅

1. **Per-Episode Tracking UI** - Implemented and deployed
   - Episode progress bar + expandable list on cards
   - Detail page shows full episode breakdown
   - All 4 test shows working (Lycoris, SNAFU, movies)

2. **VFS Reliability Fix** - Deployed
   - Increased VFS_REGENERATION_DELAY from 3s to 10s
   - Commit: `dec409a`

3. **Lycoris Recoil Fixed** - Now AVAILABLE with all 13 episodes
   - Fix: Triggered library refresh via API
   - VFS regenerated, fallback checker found it

4. **Bocchi the Rock Test** - In progress (12 eps downloading)
   - State: DOWNLOADING
   - Quality: Bluray-1080p Remux (~63 GB)

### Critical Bugs ❌

1. **SSE Connections Dropping** (HIGH PRIORITY)
   - Connections disconnect after 1-2 seconds
   - UI shows stale data (0% when actual is 31%)
   - Logs show rapid connect/disconnect pattern
   - Files: `app/routers/sse.py`, `app/core/broadcaster.py`

2. **IMPORTING State Skipped for Anime**
   - Goes DOWNLOADED → ANIME_MATCHING, skipping IMPORTING
   - Issue: `docs/issues/2026-01-22-importing-state-skipped-for-anime.md`

### UI Improvements Requested

**Issue:** `issues/ui-episode-progress-improvements.md`

1. Timeline: "grabbing" → "Grabbed" (past tense)
2. Episode Progress: Show "x downloaded, y ready" (not just ready)
3. Remove "Matching" label → show "Downloaded" for anime
4. Per-episode download % when downloading
5. New SEARCHING state for Sonarr indexer searches

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

### Key Files
| Purpose | File |
|---------|------|
| SSE endpoint | `app/routers/sse.py` |
| Broadcaster | `app/core/broadcaster.py` |
| State machine | `app/core/state_machine.py` |
| Fallback checker | `app/services/jellyfin_verifier.py` |
| qBit polling | `app/plugins/qbittorrent.py` (POLL_FAST=3, POLL_SLOW=15) |
| Card template | `app/templates/components/card.html` |
| Detail template | `app/templates/detail.html` |

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

| ID | Title | State | Episodes |
|----|-------|-------|----------|
| 7 | BOCCHI THE ROCK! | downloading | 12 (all downloading) |
| 6 | Lycoris Recoil | available | 13/13 ready |
| 5 | Rascal Dreams... | available | Movie |
| 4 | Your Name. | available | Movie |
| 2 | SNAFU | available | TV |
| 3 | Akira | available | Movie |

---

## SSE Bug Investigation Notes

**Symptom:** SSE clients disconnect after 1-2 seconds

**Logs show:**
```
04:29:57 - Client connected (1 client)
04:29:58 - Client disconnected (0 clients)  # 1 second!
04:29:58 - Client connected (1 client)
04:30:00 - Client disconnected (0 clients)  # 2 seconds!
```

**Database has correct data:**
- Progress: 31%
- Speed: 55.9 MB/s
- Polling IS working

**Possible causes:**
- Browser/proxy timeout
- Missing keepalive pings in SSE
- Error in event generator

---

## Priorities

| Priority | Task |
|----------|------|
| 1 | Fix SSE disconnection bug |
| 2 | Implement UI improvements |
| 3 | Fix IMPORTING state skipped |
| 4 | Monitor Bocchi → AVAILABLE |

---

Please read the handoff document first, then ask what to work on next.
