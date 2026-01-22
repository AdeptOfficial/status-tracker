# Status Tracker - Context Resume Prompt

**Last Updated:** 2026-01-22 (Per-Episode Tracking Session)
**Branch:** `feature/per-episode-tracking`

---

## COPY EVERYTHING BELOW TO RESUME SESSION

---

I'm continuing work on the **status-tracker** app. Read these files for context:

1. `/home/adept/git/status-tracker-workflow-fix/docs/flows/SESSION-HANDOFF-2026-01-22-PER-EPISODE.md`
2. `/home/adept/git/status-tracker-workflow-fix/DIARY.md`
3. `/home/adept/git/status-tracker-workflow-fix/docs/MVP.md`

**Working directories:**
- App code: `/home/adept/git/status-tracker-workflow-fix/`
- Homeserver docs: `/home/adept/git/homeserver/`

---

## Current Session Summary

### Completed This Session ✅

1. **Per-Episode Tracking UI** - Dashboard cards show episode progress bar + expandable list
   - Files: `app/schemas.py`, `app/routers/api.py`, `app/routers/pages.py`
   - Files: `app/templates/components/card.html`, `app/templates/detail.html`

2. **Increased Polling Speed** - qBit polling faster for responsive updates
   - File: `app/plugins/qbittorrent.py`
   - POLL_FAST: 5s → 3s, POLL_SLOW: 30s → 15s

3. **Deployed to Dev Server** - All changes live on LXC 220

### NOT YET DONE ❌

1. **Commit per-episode changes** - Deployed but NOT committed!
   ```bash
   cd /home/adept/git/status-tracker-workflow-fix
   git add -A && git commit -m "Add per-episode tracking UI, increase polling speed" && git push
   ```

2. **Lycoris Recoil stuck at anime_matching** - Shokofin VFS issue, NOT status-tracker:
   - Files in correct location: `/data/anime/shows/Lycoris Recoil/`
   - Shoko matched the series ✅
   - Shokofin VFS doesn't include it ❌
   - **Next step:** Check Shoko web UI → Import Folders

3. **Test per-episode UI** - Need working TV anime to verify UI works

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
| qBit polling | `app/plugins/qbittorrent.py` |
| Episode model | `app/models.py:299` |
| API schemas | `app/schemas.py` |
| Card template | `app/templates/components/card.html` |
| Detail template | `app/templates/detail.html` |

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
| 6 | Lycoris Recoil | anime_matching | TV/Anime (STUCK) |
| 5 | Rascal Does Not Dream... | available | Movie |
| 4 | Your Name. | available | Movie |
| 2 | SNAFU | available | TV |
| 3 | Akira | available | Movie |

---

## VFS Troubleshooting

### Check VFS contents
```bash
ssh root@10.0.2.10 "pct exec 220 -- docker exec jellyfin ls -la '/config/Shokofin/VFS/29391378-c411-8b35-b77f-84980d25f0a6/'"
```

### Library IDs
| Library | VFS ID |
|---------|--------|
| Anime Shows | `29391378-c411-8b35-b77f-84980d25f0a6` |
| Anime Movies | `abebc196-cc1b-8bbf-6f8b-b5ca7b5ad6f1` |

### Check Shokofin SignalR
```bash
ssh root@10.0.2.10 "pct exec 220 -- docker logs jellyfin 2>&1" | grep -i 'signalr.*connected'
```

---

## Roadmap

| Priority | Task |
|----------|------|
| 1 | Fix Lycoris Recoil (Shoko import folder config) |
| 2 | Commit per-episode changes |
| 3 | Test per-episode UI |
| 4 | Fix IMPORTING state skipped for anime |

---

Please read the handoff document first, then ask what to work on next.
