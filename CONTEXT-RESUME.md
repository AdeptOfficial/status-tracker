# Status Tracker - Context Resume Prompt

**Last Updated:** 2026-01-22
**Branch:** `feature/per-episode-tracking`

---

## COPY EVERYTHING BELOW TO RESUME SESSION

---

I'm continuing work on the **status-tracker** app. Read these files for context:

1. `/home/adept/git/status-tracker-workflow-fix/docs/ROADMAP.md` - Current priorities
2. `/home/adept/git/status-tracker-workflow-fix/DIARY.md` - Development history

**Working directories:**
- App code: `/home/adept/git/status-tracker-workflow-fix/`
- Homeserver docs: `/home/adept/git/homeserver/`

---

## Current State Summary

### Recently Completed

1. **SSE Heartbeat Fix** - 15s keepalive prevents connection drops
2. **"Grabbed" Label Fix** - Timeline shows past tense
3. **History Page 500 Fix** - Added selectinload for episodes
4. **Jellyseerr MEDIA_AVAILABLE Fix** - Now marks episodes + sets jellyfin_id
5. **Jellyfin Plugin Fix** - ItemAdded now marks episodes AVAILABLE
6. **Bocchi the Rock Test** - 12/12 episodes ready

### Bugs Still Open

1. **IMPORTING State Skipped** - Anime goes DOWNLOADED → ANIME_MATCHING
   - Issue: `issues/2026-01-22-importing-state-skipped-for-anime.md`

2. **Episode Progress Display** - Shows "x ready" not "x downloaded, y ready"
   - Issue: `issues/ui-episode-progress-improvements.md`

3. **Library Sync Missing IDs** - Sync button should populate missing jellyfin_id
   - Issue: `issues/library-sync-should-populate-missing-ids.md`

---

## Repo Structure

```
/
├── app/                    # Application code
├── docs/
│   ├── ROADMAP.md         # Current priorities and backlog
│   ├── reference/         # Useful reference docs
│   └── archive/           # Historical planning docs
├── issues/                 # All issues (active + resolved/)
├── features/              # Feature requests
├── DIARY.md               # Development log
└── CONTEXT-RESUME.md      # This file
```

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

Please read the ROADMAP first, then ask what to work on next.
