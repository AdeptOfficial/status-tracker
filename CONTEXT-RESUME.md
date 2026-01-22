# Status Tracker Workflow Implementation - Context Resume

**Last Updated:** 2026-01-22
**Status:** All 5 phases complete, 87 tests passing

## Project Overview

This is a **media request lifecycle tracker** for the pipeline:
```
Jellyseerr → Radarr/Sonarr → qBittorrent → Shoko (anime) → Jellyfin
```

### Problem Being Solved
- Requests were getting stuck (Lycoris Recoil at "Importing", Violet Evergarden at "Matching")
- No per-episode tracking for TV shows
- Correlation bugs causing old requests to match new webhooks

## Implementation Status

### Completed Phases

| Phase | Description | Tests |
|-------|-------------|-------|
| 0 | Test Infrastructure (pytest, fixtures, mocks) | 15 |
| 1 | Database Schema (Episode table, state renames) | - |
| 2 | Regular Movie Flow | 21 |
| 3 | Regular TV Flow + Adaptive Polling | 20 |
| 4 | Anime Movie Flow | 17 |
| 5 | Anime TV Flow | 14 |

**Total: 87 tests passing**

### The 4 Media Flows

1. **Regular Movie:** APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE
2. **Regular TV:** Same flow with per-episode tracking via Episode table
3. **Anime Movie:** ... → ANIME_MATCHING → (Jellyfin multi-type fallback) → AVAILABLE
4. **Anime TV:** Episodes individually matched by Shoko → AVAILABLE, request state aggregated

## Key Files Modified/Created

### Core Logic
- `app/plugins/shoko.py` - Major rewrite for movie vs TV handling, Jellyfin verification trigger
- `app/plugins/sonarr.py` - Episode creation on Grab, season pack Import handling
- `app/plugins/radarr.py` - is_anime detection, new field extraction
- `app/plugins/qbittorrent.py` - Adaptive polling (5s active, 30s idle)
- `app/plugins/jellyseerr.py` - Fixed poster URL, overview, year parsing
- `app/core/state_machine.py` - Added IMPORTING → ANIME_MATCHING transition
- `app/services/state_calculator.py` - Created for TV state aggregation
- `app/services/jellyfin_verifier.py` - Unified verification router, multi-type fallback

### Tests
- `tests/conftest.py` - DB fixtures, webhook loaders
- `tests/test_flow_1_regular_movie.py`
- `tests/test_flow_2_regular_tv.py`
- `tests/test_flow_3_anime_movie.py`
- `tests/test_flow_4_anime_tv.py`
- `tests/test_infrastructure.py`

### Test Fixtures
- `tests/fixtures/webhooks/` - Symlink to `docs/flows/captured-webhooks/`
- Captured webhooks: jellyseerr-movie-auto-approved, jellyseerr-tv-auto-approved, radarr-grab, radarr-import, sonarr-grab, sonarr-import

## Field Population Summary

### Movies - All fields populated:
- Jellyseerr: `jellyseerr_id`, `tmdb_id`, `overview`, `poster_url`, `year`, `title`
- Radarr Grab: `radarr_id`, `imdb_id`, `qbit_hash`, `is_anime`, `quality`, `indexer`, `file_size`, `release_group`
- Radarr Import: `final_path`
- Jellyfin: `jellyfin_id`, `available_at`
- Shoko (anime): `shoko_series_id`

### TV Shows - All fields populated:
- Jellyseerr: `jellyseerr_id`, `tvdb_id`, `overview`, `requested_seasons`
- Sonarr Grab: `sonarr_id`, `imdb_id`, `qbit_hash`, `is_anime`, `total_episodes`
- Sonarr Import: `final_path`
- Jellyfin: `jellyfin_id`, `available_at`

### Episodes - One gap:
- Sonarr Grab: `season_number`, `episode_number`, `episode_title`, `sonarr_episode_id`, `episode_tvdb_id`, `qbit_hash`
- Sonarr Import: `final_path`
- Shoko (anime): `shoko_file_id`
- **GAP:** `jellyfin_id` NOT set (MVP verifies at series level, not per-episode)

## Key Implementation Details

### Adaptive Polling (qBittorrent)
```python
POLL_FAST = 5   # seconds when downloads active (GRABBING/DOWNLOADING)
POLL_SLOW = 30  # seconds when idle
```

### State Aggregation (TV Shows)
- All AVAILABLE → request AVAILABLE
- Any FAILED → request FAILED
- Otherwise → highest priority in-progress state
- Priority: ANIME_MATCHING > IMPORTING > DOWNLOADED > DOWNLOADING > GRABBING

### Multi-Type Fallback (Anime Movies)
Shoko may recategorize anime movies as TV specials. Verification tries:
1. Movie by TMDB
2. Series by TMDB
3. Any type by TMDB
4. Title search

### Shoko Integration
- Movies: FileMatched → store shoko_series_id → trigger verify_jellyfin_availability()
- TV: FileMatched per episode → update episode.shoko_file_id → episode AVAILABLE → recalculate aggregate

## Running Tests

```bash
# All tests
docker compose run --rm \
  -v "$(pwd)/tests:/app/tests:ro" \
  -v "$(pwd)/docs:/app/docs:ro" \
  status-tracker python -m pytest tests/ -v

# Specific flow
docker compose run --rm \
  -v "$(pwd)/tests:/app/tests:ro" \
  -v "$(pwd)/docs:/app/docs:ro" \
  status-tracker python -m pytest tests/test_flow_3_anime_movie.py -v
```

## Known Gaps / Future Work

1. **Episode jellyfin_id** - Not populated (MVP verifies series-level)
2. **Per-episode Jellyfin verification** - Could add for more granular tracking
3. **Shoko cross-reference details** - Currently just storing file_id, could extract AniDB IDs

## Plan File Location

Full implementation plan: `/home/adept/.claude/plans/zazzy-whistling-mochi.md`
