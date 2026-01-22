# Status Tracker - Context Resume Prompt

**Last Updated:** 2026-01-22 (SSE Fix + VFS Refresh Session)
**Branch:** `fix/media-workflow-audit`

---

## COPY EVERYTHING BELOW TO RESUME SESSION

---

I'm continuing work on the **status-tracker** app. Read these files for context:

1. `/home/adept/git/status-tracker-workflow-fix/docs/flows/SESSION-HANDOFF-2026-01-22-SSE-FIX.md`
2. `/home/adept/git/status-tracker-workflow-fix/DIARY.md`
3. `/home/adept/git/status-tracker-workflow-fix/docs/MVP.md`

**Working directories:**
- App code: `/home/adept/git/status-tracker-workflow-fix/`
- Homeserver docs: `/home/adept/git/homeserver/`

---

## Current Session Summary

### Completed This Session ✅

1. **Fixed SSE Live Updates** - Renamed `sse:refresh` → `status-update` (htmx reserved prefix conflict)
   - Files: `app/templates/index.html`, `app/templates/detail.html`

2. **Added Diagnostic Logging** - Broadcast tracking for debugging
   - Files: `app/core/broadcaster.py`, `app/routers/sse.py`

3. **Enhanced Fallback Checker** - Now triggers Jellyfin library scan for `ANIME_MATCHING` requests to force Shokofin VFS regeneration
   - File: `app/services/jellyfin_verifier.py`
   - Tested successfully with "Rascal Does Not Dream of a Dreaming Girl"

4. **Created Issue** - IMPORTING state skipped for anime
   - File: `docs/issues/2026-01-22-importing-state-skipped-for-anime.md`

### NOT YET DONE ❌

1. **Commit changes** - All above changes are uncommitted!
   ```bash
   cd /home/adept/git/status-tracker-workflow-fix
   git add -A && git commit -m "Add VFS refresh to fallback checker, diagnostic logging" && git push
   ```

2. **Per-episode monitoring gap** - Episodes ARE created in DB but NOT displayed:
   - `Episode` model exists (`app/models.py:299`)
   - Episodes created on Sonarr grab (`app/plugins/sonarr.py`)
   - `EpisodeResponse` schema exists (`app/schemas.py:91`)
   - **MISSING:** `episodes` field not in `MediaRequestResponse` schema
   - **MISSING:** UI doesn't show per-episode progress
   - Issue file: `issues/per-episode-download-tracking.md`

3. **Test Lycoris Recoil** - TV anime currently at `approved` state

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
| State machine | `app/core/state_machine.py` |
| Broadcaster | `app/core/broadcaster.py` |
| Fallback checker | `app/services/jellyfin_verifier.py` |
| Sonarr plugin | `app/plugins/sonarr.py` |
| Episode model | `app/models.py:299` |
| API schemas | `app/schemas.py` |
| Templates | `app/templates/index.html`, `detail.html` |

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

| ID | Title | State | Type |
|----|-------|-------|------|
| 6 | Lycoris Recoil | approved | TV/Anime |
| 5 | Rascal Does Not Dream... | available | Movie |
| 4 | Your Name. | available | Movie |
| 2 | SNAFU | available | TV |
| 3 | Akira | available | Movie |

---

## Roadmap (from DIARY.md)

| Priority | Task |
|----------|------|
| 1 | Fix IMPORTING state skipped for anime |
| 2 | Test anime TV shows |
| 3 | Media sync button |
| 4 | Fix delete integration |

---

Please read the handoff document first, then ask what to work on next.
