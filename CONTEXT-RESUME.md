# Status Tracker - Context Resume Prompt

**Last Updated:** 2026-01-22 (Bug Fixes Session)
**Branch:** `feature/per-episode-tracking`

---

## COPY EVERYTHING BELOW TO RESUME SESSION

---

I'm continuing work on the **status-tracker** app. Read these files for context:

1. `/home/adept/git/status-tracker-workflow-fix/docs/flows/SESSION-HANDOFF-2026-01-22-FIXES.md`
2. `/home/adept/git/status-tracker-workflow-fix/DIARY.md`
3. `/home/adept/git/status-tracker-workflow-fix/issues/ui-episode-progress-improvements.md`

**Working directories:**
- App code: `/home/adept/git/status-tracker-workflow-fix/`
- Homeserver docs: `/home/adept/git/homeserver/`

---

## Current State Summary

### Completed This Session ✅

1. **SSE Heartbeat Fix** - 15s keepalive prevents connection drops
   - File: `app/core/broadcaster.py`
   - Issue: `issues/sse-connections-dropping.md`

2. **"Grabbed" Label Fix** - Timeline shows past tense
   - Files: `app/templates/detail.html`, `card.html`

3. **History Page 500 Fix** - Added selectinload for episodes
   - File: `app/routers/pages.py`
   - Issue: `issues/history-page-500-error.md`

4. **Jellyseerr MEDIA_AVAILABLE Fix** - Now marks episodes + sets jellyfin_id
   - File: `app/plugins/jellyseerr.py`
   - Issue: `issues/jellyseerr-media-available-incomplete.md`

5. **Jellyfin Plugin Fix** - ItemAdded now marks episodes AVAILABLE
   - File: `app/plugins/jellyfin.py`

6. **Bocchi the Rock Test** - Full flow completed
   - 12 episodes, 63GB Remux, VFS auto-regenerated
   - Data manually fixed (episodes + jellyfin_id)

### All Paths to AVAILABLE Now Set Required Fields

| Path | jellyfin_id | Episodes | Status |
|------|-------------|----------|--------|
| Fallback checker | ✅ | ✅ | Was working |
| Jellyseerr webhook | ✅ | ✅ | Fixed this session |
| Jellyfin webhook | ✅ | ✅ | Fixed this session |
| Library sync | ✅ | N/A | Was working |

### Bugs Still Open ❌

1. **IMPORTING State Skipped** - Anime goes DOWNLOADED → ANIME_MATCHING
   - Issue: `docs/issues/2026-01-22-importing-state-skipped-for-anime.md`

2. **Episode Progress Display** - Shows "x ready" not "x downloaded, y ready"
   - Issue: `issues/ui-episode-progress-improvements.md`

### UI Improvements Requested (Not Done Yet)

From `issues/ui-episode-progress-improvements.md`:
1. ~~Timeline: "grabbing" → "Grabbed"~~ ✅ DONE
2. Episode Progress: "x downloaded, y ready" (not just "x ready")
3. Per-episode download %
4. Remove "Matching" label for anime TV
5. New SEARCHING state

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
| SSE heartbeat | `app/core/broadcaster.py` (SSE_HEARTBEAT_INTERVAL=15) |
| Fallback checker | `app/services/jellyfin_verifier.py` |
| Jellyseerr plugin | `app/plugins/jellyseerr.py` |
| Jellyfin plugin | `app/plugins/jellyfin.py` |
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
| 7 | BOCCHI THE ROCK! | available | 12/12 ready ✅ (fixed) |
| 6 | Lycoris Recoil | available | 13/13 ready |
| 5 | Rascal Dreams... | available | Movie |
| 4 | Your Name. | available | Movie |
| 2 | SNAFU | available | 13/13 ready |
| 3 | Akira | available | Movie |

---

## Priorities

| Priority | Task |
|----------|------|
| 1 | Test SSE heartbeat stability (should stay connected >15s now) |
| 2 | Implement remaining UI improvements |
| 3 | Fix IMPORTING state skipped for anime |
| 4 | Commit all changes to git |

---

Please read the handoff document first, then ask what to work on next.
