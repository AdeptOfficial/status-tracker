# Session Handoff - 2026-01-22 (Updated)

## Context

Working on status-tracker architecture redesign in `~/git/status-tracker-workflow-fix/` (branch: fix/media-workflow-audit).

## What Was Accomplished This Session

### Webhook Investigation Complete

Captured ALL webhook payloads from test requests:
- Violet Evergarden: The Movie (2020) - anime movie
- Violet Evergarden: Recollections (2021) - special/recap
- Lycoris Recoil (2022) - TV anime (13 episodes)

### Key Findings

1. **`downloadId` = qBit hash** - 40-char uppercase hex, confirmed for both Radarr and Sonarr
2. **Sonarr Grab has `episodes[]`** - Full episode list with titles, no API call needed
3. **`series.type == "anime"`** - Early is_anime detection at Phase 2
4. **Specials = movies** - No special media_type, handled by Radarr
5. **Season pack Import = ONE webhook** - `episodeFiles[]` (plural) with all 13 files
6. **Shoko uses SignalR** at `shoko:8111/signalr/aggregate?feeds=shoko,file`
7. **Shoko movie events:** FileDetected → FileHashed → FileMatched → SeriesUpdated
8. **Shoko TV events:** FileHashed (×13) → SeriesUpdated → EpisodeUpdated (×78+)

### Documentation Updated

- `docs/flows/phase-4-import.md` - Rewritten with per-episode model, Sonarr season pack format
- `docs/flows/phase-5-verification.md` - Added real Shoko SignalR events
- `docs/flows/investigation-findings.md` - Complete findings documented
- `docs/flows/database.md` - Fixed states (DOWNLOADED not DOWNLOAD_DONE)
- `docs/MVP.md` - Added webhook findings, per-episode tracking in scope

### Captured Webhooks (All Complete)

```
docs/flows/captured-webhooks/
├── jellyseerr-movie-auto-approved.json
├── jellyseerr-tv-auto-approved.json
├── radarr-grab.json
├── sonarr-grab.json
├── radarr-import.json
└── sonarr-import.json
```

## Pending Tasks

- [x] Update Phase 2 doc for per-episode model ✓
- [x] Remove TEMP payload logging from webhooks.py ✓
- [x] Update per-episode-tracking.md with findings ✓

## Key Architecture Decisions

1. **9 States**: REQUESTED, APPROVED, GRABBING, DOWNLOADING, DOWNLOADED, IMPORTING, ANIME_MATCHING, AVAILABLE, FAILED
2. **Per-episode tracking for TV** - Episode table with individual state per episode
3. **Season pack handling**: All episodes share same qbit_hash, ONE Import webhook with `episodeFiles[]`
4. **is_anime detection at Phase 2** from `movie.tags` or `series.type`
5. **Shoko correlation via `final_path`**, not title matching

## Key Files

1. `docs/flows/investigation-findings.md` - All webhook findings
2. `docs/flows/captured-webhooks/*.json` - Raw payloads
3. `docs/flows/per-episode-tracking.md` - Episode architecture
4. `docs/flows/phase-*.md` - Phase documentation (1-5)
5. `docs/MVP.md` - Updated MVP scope
6. `docs/flows/database.md` - Schema with Episode table

## Dev Server Access

```
LXC 220 on 10.0.2.10
IP: 10.0.2.20
Port: 8100
Path: /opt/status-tracker/
```

Check logs: `ssh root@10.0.2.10 "pct exec 220 -- bash -c 'cd /opt/status-tracker && docker compose logs --tail=100 status-tracker'"`

## Security Reminders

- DO NOT read .env files
- DO NOT run printenv/docker inspect
- ASK before SSH operations
