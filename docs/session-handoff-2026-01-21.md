# Session Handoff: Status-Tracker Architecture Redesign

**Date:** 2026-01-21
**Branch:** `fix/media-workflow-audit` in `~/git/status-tracker-workflow-fix/`

## Current Task

Redesigning status-tracker architecture to fix fundamental flow issues. User wants to dive deep into **Request Addition** flow.

## Key Documents Created

1. `~/git/status-tracker-workflow-fix/docs/media-workflow-audit.md` - Bug findings from testing
2. `~/git/status-tracker-workflow-fix/docs/flow-redesign-plan.md` - Flow divergence analysis
3. `~/git/status-tracker-workflow-fix/docs/architecture-v2.md` - **MAIN DOC** - Full architecture

## Bugs Found During Testing

| # | Bug | Impact |
|---|-----|--------|
| 1 | Correlation matches wrong request | Webhooks update old AVAILABLE request instead of new one |
| 2 | TV fallback missing | `media_type == "movie"` filter + no TVDB lookup |
| 3 | Anime ID mismatch | Shoko uses AniDB, we search by TMDB |
| 4 | Poster URL missing | Not fetched from TMDB |
| 5 | Library sync phantom requests | Creates requests user didn't make |

## Architecture Overview (4 Paths)

```
COMMON:  Jellyseerr → APPROVED → Grab → INDEXED → DOWNLOADING → IMPORTING
                                                                    │
         ┌──────────────────┬──────────────────┬────────────────────┤
         ▼                  ▼                  ▼                    ▼
    Regular Movie      Regular TV        Anime Movie           Anime TV
    (TMDB lookup)     (TVDB lookup)    (TMDB + Shoko)       (TVDB + Shoko)
```

## Request Addition Phases (from architecture-v2.md)

1. **Request Creation** - Jellyseerr webhook → create request
2. **Indexer Grab** - Radarr/Sonarr Grab → store download_id (qbit hash)
3. **Download Progress** - qBit polling → update progress
4. **Import** - Radarr/Sonarr Import → store final_path, DIVERGE here
5. **Verification** - Different per path (TMDB/TVDB/Shoko lookup)

## Key Correlation Fix Needed

```python
# CURRENT (broken): Finds ANY request, even AVAILABLE ones
request = await correlator.find_by_any(db, tmdb_id=tmdb_id)

# PROPOSED: Prioritize by download_id, exclude completed requests
request = await correlator.find_active_by_any(
    db,
    download_id=download_id,  # PRIMARY - unique per download
    tmdb_id=tmdb_id,
    exclude_states=[RequestState.AVAILABLE, RequestState.DELETED],
    order_by="created_at DESC",
)
```

## Security Protocols

- Never read `.env`, `config.xml`, `settings.json` without explicit request
- Never run `printenv`, `env`, `docker inspect`, `docker-compose config`
- SSH access: `ssh root@10.0.2.10` then `pct enter 220` for media LXC

## Next Step

User wants to **dive deep into Request Addition** - hammer out the exact steps for all 4 paths, especially:
- What data comes from each webhook
- What correlation keys to use at each step
- How to handle edge cases

## Files to Read

1. `~/git/status-tracker-workflow-fix/docs/architecture-v2.md` - Full architecture
2. `~/git/status-tracker-workflow-fix/app/core/correlator.py` - Current correlator code
3. `~/git/status-tracker-workflow-fix/app/plugins/` - Webhook handlers
