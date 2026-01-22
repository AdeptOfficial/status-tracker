# Implementation Plan: Media Workflow Redesign

**Goal:** Fix stuck requests and implement 4 media flows with proper testing.

**Reference:** See `IMPLEMENTATION-REFERENCE.md` for detailed code snippets.

**Current Problems (from screenshot):**
- Lycoris Recoil: Stuck at "Importing", shows only "S01E01" (missing 12 episodes)
- Violet Evergarden: Stuck at "Matching" (ANIME_MATCHING never completes)

---

## Implementation Order

Test one flow at a time, building incrementally:

```
┌───────┬─────────────────────┬──────────────────────────────────────────┐
│ Phase │        Flow         │                   Adds                   │
├───────┼─────────────────────┼──────────────────────────────────────────┤
│ 0     │ Test Infrastructure │ pytest, fixtures, mocks                  │
├───────┼─────────────────────┼──────────────────────────────────────────┤
│ 1     │ Database Updates    │ Episode table, state renames, new fields │
├───────┼─────────────────────┼──────────────────────────────────────────┤
│ 2     │ Regular Movie       │ Core flow without episodes or Shoko      │
├───────┼─────────────────────┼──────────────────────────────────────────┤
│ 3     │ Regular TV          │ Episode table, per-episode tracking      │
├───────┼─────────────────────┼──────────────────────────────────────────┤
│ 4     │ Anime Movie         │ Shoko verification, multi-type fallback  │
├───────┼─────────────────────┼──────────────────────────────────────────┤
│ 5     │ Anime TV            │ Episode + Shoko combined                 │
└───────┴─────────────────────┴──────────────────────────────────────────┘
```

---

## Phase 0: Test Infrastructure

**Create:**
```
tests/
├── conftest.py              # DB fixtures, webhook loaders
├── fixtures/
│   └── webhooks/            # Symlink to docs/flows/captured-webhooks/
└── mocks/
    ├── qbittorrent.py       # Mock download progress
    ├── jellyfin.py          # Mock verification responses
    └── shoko.py             # Mock SignalR events
```

**conftest.py essentials:**
- In-memory SQLite async database
- `async_session` fixture
- `load_webhook(name)` helper to load captured JSON

**Requirements:** `pytest`, `pytest-asyncio`, `aiosqlite`

**Acceptance:** `pytest tests/` runs without errors

---

## Phase 1: Database Schema Updates

### 1.1 State Renames

```python
class RequestState(str, enum.Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    GRABBING = "grabbing"          # was INDEXED
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"      # was DOWNLOAD_DONE
    IMPORTING = "importing"
    ANIME_MATCHING = "anime_matching"
    AVAILABLE = "available"
    FAILED = "failed"
```

### 1.2 MediaRequest New Fields

- `is_anime: bool` - Detection flag
- `imdb_id: str` - From Radarr/Sonarr Grab
- `overview: str` - From Jellyseerr message
- `file_size: int`, `release_group: str` - Release info
- `requested_seasons: str`, `total_episodes: int` - TV-specific
- `available_at: datetime` - Completion timestamp
- `episodes` - Relationship to Episode table

### 1.3 Episode Model (NEW)

Core fields: `season_number`, `episode_number`, `episode_title`, `state`, `qbit_hash`, `final_path`

Service IDs: `sonarr_episode_id`, `episode_tvdb_id`, `shoko_file_id`, `jellyfin_id`

### 1.4 State Machine Updates

Update `VALID_TRANSITIONS` in `app/core/state_machine.py` with new state names.

**Acceptance:** App starts, Episode table created, all ID fields present

---

## Phase 2: Flow 1 - Regular Movie

**Flow:** `APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE`

### 2.1 Bug Fixes Required

**correlator.py:** Remove `AVAILABLE` from `ACTIVE_STATES`

**jellyseerr.py:** Fix poster URL (`payload.get("image")`), extract overview, parse year from subject

### 2.2 Radarr Handlers

**Grab:** Store `qbit_hash`, `radarr_id`, `imdb_id`, detect `is_anime` from tags, set state `GRABBING`

**Import:** Store `final_path`, route to `IMPORTING` or `ANIME_MATCHING` based on `is_anime`

### 2.3 Regular Movie Verification

Search Jellyfin by TMDB ID, verify playable, set `AVAILABLE`

### 2.4 Tests

- `test_regular_movie_full_flow` - Complete flow APPROVED → AVAILABLE
- `test_correlation_excludes_available` - New request doesn't match old AVAILABLE

**Acceptance:** Regular movie reaches AVAILABLE, correlation bug fixed

---

## Phase 3: Flow 2 - Regular TV

**Flow:** Same states, but with Episode table

### 3.1 Sonarr Grab Handler

Create Episode rows from `payload["episodes"]` - titles come from webhook, no API needed!

All episodes share same `qbit_hash` for season packs.

### 3.2 Sonarr Import Handler

Handle both `episodeFiles[]` (season pack) and `episodeFile` (single).

Match episodes by season/episode number, set `final_path` and state.

### 3.3 State Aggregation

New file `app/services/state_calculator.py`:
- All AVAILABLE → request AVAILABLE
- Any FAILED → request FAILED
- Otherwise → highest priority in-progress state

### 3.4 qBit Poller Updates

Query Episode table by `qbit_hash`, update all episodes with same hash together.

**Adaptive polling (from MVP Q10):**
- Active downloads: poll every 5 seconds
- No active downloads: poll every 30 seconds

```python
POLL_FAST = 5   # seconds when downloads active
POLL_SLOW = 30  # seconds when idle

async def get_poll_interval(db: AsyncSession) -> int:
    active = await db.scalar(
        select(func.count()).where(
            MediaRequest.state.in_([RequestState.GRABBING, RequestState.DOWNLOADING])
        )
    )
    return POLL_FAST if active > 0 else POLL_SLOW
```

### 3.5 Fix Fallback Checker (Bug #2)

Remove `media_type == "movie"` filter - check both movies AND TV!

### 3.6 Jellyfin TVDB Lookup

Add `find_item_by_provider_id(provider, id, type)` to jellyfin client.

### 3.7 Tests

- `test_regular_tv_episode_creation` - 13 episodes created from Grab
- `test_season_pack_import` - One webhook updates all episodes
- `test_episode_state_aggregation` - Request state derived from episodes

**Acceptance:** 13 episodes created, all reach AVAILABLE

---

## Phase 4: Flow 3 - Anime Movie

**Flow:** `... → IMPORTING → ANIME_MATCHING → AVAILABLE`

### 4.1 Multi-Type Fallback Verification

Try: Movie by TMDB → Series by TMDB → Any type → Title search

This fixes Violet Evergarden stuck at MATCHING (Shoko categorizes as TV Special).

### 4.2 Shoko FileMatched Handler

Match by `final_path` to request, trigger verification if `has_cross_refs`.

### 4.3 Tests

- `test_anime_movie_detection` - `is_anime=True` from movie.tags
- `test_anime_movie_goes_through_matching` - Routes to ANIME_MATCHING
- `test_anime_movie_recategorization_fallback` - Finds as Series when Movie fails

**Acceptance:** Anime movie reaches AVAILABLE via Shoko or fallback

---

## Phase 5: Flow 4 - Anime TV

**Flow:** Episodes go through `ANIME_MATCHING` individually

### 5.1 Shoko FileMatched for TV Episodes

Match by `final_path` to Episode row, update individual episode state, recalculate parent request state.

### 5.2 Unified Verification Router

```python
async def verify_request(request, db):
    if request.is_anime:
        return verify_anime_movie/tv(request, db)
    else:
        return verify_regular_movie/tv(request, db)
```

### 5.3 Tests

- `test_anime_tv_detection` - `is_anime=True` from series.type
- `test_anime_tv_episodes_anime_matching` - 13 episodes at ANIME_MATCHING
- `test_anime_tv_partial_progress` - 5/13 matched shows partial
- `test_anime_tv_all_episodes_available` - All matched → AVAILABLE

**Acceptance:** All 13 episodes reach AVAILABLE

---

## Files Summary

```
┌────────┬───────────────────────────────────┬───────┐
│ Action │               File                │ Phase │
├────────┼───────────────────────────────────┼───────┤
│ CREATE │ tests/conftest.py                 │ 0     │
├────────┼───────────────────────────────────┼───────┤
│ CREATE │ tests/mocks/                      │ 0     │
├────────┼───────────────────────────────────┼───────┤
│ CREATE │ tests/test_flow_*.py              │ 2-5   │
├────────┼───────────────────────────────────┼───────┤
│ CREATE │ app/services/state_calculator.py  │ 3     │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/models.py                     │ 1     │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/core/correlator.py            │ 2     │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/core/state_machine.py         │ 1     │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/plugins/jellyseerr.py         │ 2     │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/plugins/radarr.py             │ 2     │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/plugins/sonarr.py             │ 3     │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/plugins/qbittorrent.py        │ 3     │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/plugins/shoko.py              │ 4, 5  │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/clients/jellyfin.py           │ 3     │
├────────┼───────────────────────────────────┼───────┤
│ MODIFY │ app/services/jellyfin_verifier.py │ 2-5   │
└────────┴───────────────────────────────────┴───────┘
```

---

## Verification

After each phase:
```bash
pytest tests/test_flow_N_*.py -v
```

After all phases:
```bash
pytest tests/ -v
./deploy.sh dev
```

---

## Extensibility Pattern

Adding a new field = 2 steps:

**1. Add to model** (`app/models.py`):
```python
new_field: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
```

**2. Extract in plugin** (e.g., `app/plugins/radarr.py`):
```python
request.new_field = payload.get("someObject", {}).get("newField")
```

Captured webhooks in `docs/flows/captured-webhooks/` show all available fields.

---

## Post-MVP Follow-ups

- [ ] **Timezone display:** Ensure frontend converts UTC timestamps to user's browser timezone
- [ ] **Pydantic deprecation:** Update `app/config.py` to use `ConfigDict` instead of class-based config
- [ ] **datetime.utcnow() deprecation:** Replace with `datetime.now(datetime.UTC)`
- [ ] **Test RuntimeWarning:** Suppress or fix "coroutine never awaited" warning in Shoko tests (mock `create_task` properly)

---

## Definition of Done

- [ ] All 4 test files pass
- [ ] State names corrected (GRABBING, DOWNLOADED)
- [ ] Episode table works for TV
- [ ] Correlation bug fixed (AVAILABLE not in active states)
- [ ] TV fallback working (no media_type filter)
- [ ] Anime detection at Grab time
- [ ] Multi-type fallback for recategorized anime
- [ ] Lycoris Recoil reaches AVAILABLE with 13 episodes
- [ ] Violet Evergarden: Recollections reaches AVAILABLE
