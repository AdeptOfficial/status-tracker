# Session Handoff: Status-Tracker Architecture Redesign

**Date:** 2026-01-21 (Updated)
**Branch:** `fix/media-workflow-audit` in `~/git/status-tracker-workflow-fix/`

## Current Task

Redesigning status-tracker architecture. Documenting all 5 phases with flow diagrams, current implementation bugs, and fixes.

## Progress

| Phase | Status | Key Changes |
|-------|--------|-------------|
| Phase 1 - Request Creation | ✅ Done | Year parsing, poster URL fix, duplicate handling |
| Phase 2 - Indexer Grab | ✅ Done | GRABBING state for TV, qbit_hashes array, episode tracking |
| Phase 3 - Download Progress | 🔄 In Progress | Started reading, need to update for multi-hash TV |
| Phase 4 - Import | ⏳ Pending | |
| Phase 5 - Verification | ⏳ Pending | |

## Key Documents Created/Updated

1. `~/git/status-tracker-workflow-fix/docs/MVP.md` - **MVP definition**
2. `~/git/status-tracker-workflow-fix/docs/flows/README.md` - Flow overview
3. `~/git/status-tracker-workflow-fix/docs/flows/database.md` - **Schema with states**
4. `~/git/status-tracker-workflow-fix/docs/flows/phase-1-request-creation.md` - ✅ Complete
5. `~/git/status-tracker-workflow-fix/docs/flows/phase-2-indexer-grab.md` - ✅ Complete
6. `~/git/status-tracker-workflow-fix/docs/flows/phase-3-download-progress.md` - 🔄 Needs update
7. `~/git/status-tracker-workflow-fix/docs/features/sse-live-updates.md` - SSE spec (post-MVP)

## Finalized States

```
REQUESTED      ← User requested, awaiting admin approval
APPROVED       ← Approved, waiting for Radarr/Sonarr to grab
GRABBING       ← TV only: grabbing episodes ("Grabbed 3/12 eps")
DOWNLOADING    ← qBit downloading
DOWNLOAD_DONE  ← qBit complete, waiting for import (debug stuck imports)
IMPORTING      ← Radarr/Sonarr importing to library
ANIME_MATCHING ← Anime only: waiting for Shoko to match
AVAILABLE      ← In Jellyfin, ready to watch
FAILED         ← Error occurred (for debugging)
```

**Key decisions:**
- Movies skip GRABBING (single file)
- TV uses GRABBING with episode count ("3/12 eps")
- DOWNLOAD_DONE kept for debugging stuck imports
- `qbit_hash` → `qbit_hashes` (JSON array for TV with multiple episode hashes)

## Database Schema Changes

```
# Changed
qbit_hash → qbit_hashes (JSON array)

# Added
grabbed_episodes     ← TV: count grabbed
downloaded_episodes  ← TV: count downloaded
imported_episodes    ← TV: count imported
total_episodes       ← TV: target count
```

## Bugs Documented

| Bug | Location | Status |
|-----|----------|--------|
| Poster URL wrong field | jellyseerr.py | Documented |
| Correlation no state filtering | correlator.py, radarr.py, sonarr.py | Documented |
| Year not extracted | jellyseerr.py | Documented |
| TV fallback missing | jellyfin_verifier.py | Documented |
| Sonarr only stores first episode | sonarr.py | Documented |
| Single qbit_hash field | models.py | Documented |

## MVP Scope

**In:** 4 flows working, state tracking, correlation fix, fallback checker
**Out:** SSE live updates, download progress %, per-episode tracking

## Security Protocols

- Never read `.env`, `config.xml`, `settings.json` without explicit request
- Never run `printenv`, `env`, `docker inspect`, `docker-compose config`
- SSH access: `ssh root@<dev-proxmox>` then `pct enter <media-dev-vmid>` for media LXC

## Next Steps

1. [ ] Update Phase 3 doc for multi-hash TV handling
2. [ ] Document Phase 4 (Import)
3. [ ] Document Phase 5 (Verification - 4 paths)
4. [ ] Capture live Sonarr Grab webhook (nice-to-have)

## Files to Read First

1. `~/git/status-tracker-workflow-fix/docs/MVP.md` - What "done" looks like
2. `~/git/status-tracker-workflow-fix/docs/flows/database.md` - Schema with states
3. `~/git/status-tracker-workflow-fix/docs/flows/phase-2-indexer-grab.md` - Most recent work
