# Phase 5: Verification

**Source:** Varies by media path
**Trigger:** Jellyfin webhook, Shoko SignalR, or fallback polling
**State Transition:** `IMPORTING` → `AVAILABLE` (or `ANIME_MATCHING` → `AVAILABLE`)

---

## Overview

This is the **divergence point** where the 4 media paths split:

| Path | Type | Verification Method |
|------|------|---------------------|
| 5a | Regular Movie | Jellyfin TMDB lookup |
| 5b | Regular TV | Jellyfin TVDB lookup |
| 5c | Anime Movie | Shoko SignalR → Jellyfin |
| 5d | Anime TV | Shoko SignalR → Jellyfin |

---

## Path 5a: Regular Movie

### Trigger Options

1. **Jellyfin webhook:** `ItemAdded` (ItemType=Movie)
2. **Fallback polling:** Every 30 seconds

### Jellyfin Search API

```
GET /Items?IncludeItemTypes=Movie&AnyProviderIdEquals=Tmdb.{tmdb_id}
```

### Correlation

Match request's `tmdb_id` to Jellyfin's provider IDs.

### State Transition

```
IMPORTING → AVAILABLE
```

### Implementation

```python
async def verify_movie_in_jellyfin(request: MediaRequest) -> bool:
    if not request.tmdb_id:
        return False

    items = await jellyfin.get(
        f"/Items?IncludeItemTypes=Movie&AnyProviderIdEquals=Tmdb.{request.tmdb_id}"
    )

    if items.get("TotalRecordCount", 0) > 0:
        request.jellyfin_id = items["Items"][0]["Id"]
        request.state = RequestState.AVAILABLE
        return True

    return False
```

---

## Path 5b: Regular TV

### Trigger Options

1. **Jellyfin webhook:** `ItemAdded` (ItemType=Episode)
2. **Fallback polling:** Every 30 seconds

### Jellyfin Search API

```
GET /Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tvdb.{tvdb_id}
```

### Correlation

Match request's `tvdb_id` to Jellyfin's provider IDs.

### Per-Episode Verification

For TV shows with Episode table:

```python
# Option A: Verify series exists (aggregate)
if series_in_jellyfin(tvdb_id):
    for episode in request.episodes:
        episode.state = EpisodeState.AVAILABLE
    request.state = RequestState.AVAILABLE

# Option B: Verify each episode (granular) - post-MVP
for episode in request.episodes:
    if episode_in_jellyfin(tvdb_id, season, episode_num):
        episode.state = EpisodeState.AVAILABLE
```

**MVP decision:** Option A (series-level verification). Per-episode is overkill.

### State Transition

```
Episode states:  IMPORTING → AVAILABLE (all at once)
Request state:   IMPORTING → AVAILABLE (aggregate)
```

### Bug #2: TV Fallback Missing

**Current (Broken):** Fallback checker has `media_type == "movie"` filter.

```python
# BUG in jellyfin_verifier.py line 170-174
stmt = select(MediaRequest).where(
    MediaRequest.state.in_([RequestState.ANIME_MATCHING, RequestState.IMPORTING]),
    MediaRequest.media_type == "movie",  # BUG: Excludes TV!
)
```

**Fix:**

```python
stmt = select(MediaRequest).where(
    MediaRequest.state.in_([RequestState.ANIME_MATCHING, RequestState.IMPORTING]),
    # Remove movie filter
    or_(
        MediaRequest.tmdb_id.isnot(None),
        MediaRequest.tvdb_id.isnot(None),
    ),
)
```

### Implementation

```python
async def verify_tv_in_jellyfin(request: MediaRequest) -> bool:
    if not request.tvdb_id:
        # Fallback to TMDB
        return await verify_by_tmdb(request, "Series")

    items = await jellyfin.get(
        f"/Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tvdb.{request.tvdb_id}"
    )

    if items.get("TotalRecordCount", 0) > 0:
        request.jellyfin_id = items["Items"][0]["Id"]
        request.state = RequestState.AVAILABLE
        return True

    return False
```

---

## Path 5c: Anime Movie

### Trigger

Shoko SignalR events via hub connection.

### Shoko SignalR Connection

```
Hub URL: http://shoko:8111/signalr/aggregate?feeds=shoko,file
```

### Shoko Event Sequence (Observed 2026-01-21)

```
1. ShokoEvent:FileDetected   ← File seen by Shoko
2. ShokoEvent:FileHashed     ← File hash computed
3. ShokoEvent:FileMatched    ← Matched to AniDB (THIS IS THE KEY ONE)
4. ShokoEvent:SeriesUpdated  ← Series metadata updated
```

**From logs:**
```
22:36:40 - ShokoEvent:FileDetected (no handler)
22:36:58 - ShokoEvent:FileHashed (no handler)
22:36:59 - Shoko file matched → Request transitions importing → anime_matching
22:36:59 - ShokoEvent:SeriesUpdated (no handler)
```

### FileMatched Event (Expected Format)

```json
{
  "EventType": "FileMatched",
  "FileInfo": {
    "FileID": 12345,
    "RelativePath": "anime/movies/Chainsaw Man - Reze Arc/movie.mkv",
    "CrossReferences": [
      {
        "AniDBID": 12345,
        "AniDBType": "Movie"
      }
    ]
  }
}
```

### Correlation

1. **Primary:** `final_path` matches `/data/{RelativePath}`
2. **Fallback:** Filename pattern match

```python
def match_shoko_file_to_request(file_info: dict, requests: list) -> MediaRequest | None:
    relative_path = file_info.get("RelativePath", "")

    for request in requests:
        if not request.final_path:
            continue

        # Primary: Exact path match
        if request.final_path.endswith(relative_path):
            return request

        # Fallback: Filename match
        request_filename = os.path.basename(request.final_path)
        file_filename = os.path.basename(relative_path)
        if request_filename == file_filename:
            return request

    return None
```

### State Flow

```
IMPORTING → FileMatched(cross_refs=true)  → AVAILABLE
IMPORTING → FileMatched(cross_refs=false) → ANIME_MATCHING → Fallback → AVAILABLE
```

### Fallback Verification (ANIME_MATCHING)

If stuck at `ANIME_MATCHING`, try multiple Jellyfin lookups:

```python
async def verify_anime_movie_fallback(request: MediaRequest) -> bool:
    # Try 1: Movie by TMDB
    if item := await find_by_tmdb(request.tmdb_id, "Movie"):
        return mark_available(request, item)

    # Try 2: Series by TMDB (Shoko may categorize as TV)
    if item := await find_by_tmdb(request.tmdb_id, "Series"):
        return mark_available(request, item)

    # Try 3: Any type by TMDB
    if item := await find_by_tmdb(request.tmdb_id):
        return mark_available(request, item)

    # Try 4: Title search (last resort)
    if item := await search_by_title(request.title, request.year):
        return mark_available(request, item)

    return False
```

### Bug #3: Anime ID Mismatch

**Problem:** Jellyseerr requests as Movie (TMDB), but Shoko categorizes as TV Special (AniDB).

**Example:** Violet Evergarden compilation movies
- Jellyseerr: Movie (TMDB 1052946)
- Shoko: TV Special (AniDB 12138)
- Shokofin: Presents as TV episodes
- Fallback: Searches for Movie, finds nothing

**Fix:** The dual search fallback above handles this.

---

## Path 5d: Anime TV

### Trigger

Shoko SignalR events - **different from movies!**

### Shoko TV Event Sequence (Observed 2026-01-21)

For TV series with 13 episodes:
```
22:40:10 - ShokoEvent:FileHashed (×13, one per file)
22:40:13 - ShokoEvent:SeriesUpdated
22:40:13 - ShokoEvent:EpisodeUpdated (×78+ events!)
```

**Key difference from movies:** TV uses `EpisodeUpdated` events, not `FileMatched`.

The many EpisodeUpdated events are because Shoko updates episode metadata multiple times during processing.

### Correlation

Same as Path 5c - match `final_path` to Shoko's `RelativePath`.

### State Flow

```
IMPORTING → FileMatched(cross_refs=true)  → AVAILABLE
IMPORTING → FileMatched(cross_refs=false) → ANIME_MATCHING → Fallback → AVAILABLE
```

### Fallback Verification

```python
async def verify_anime_tv_fallback(request: MediaRequest) -> bool:
    # Try 1: Series by TVDB
    if request.tvdb_id:
        if item := await find_by_tvdb(request.tvdb_id, "Series"):
            return mark_available(request, item)

    # Try 2: Series by TMDB
    if request.tmdb_id:
        if item := await find_by_tmdb(request.tmdb_id, "Series"):
            return mark_available(request, item)

    # Try 3: Any type by TMDB
    if item := await find_by_tmdb(request.tmdb_id):
        return mark_available(request, item)

    # Try 4: Title search
    if item := await search_by_title(request.title):
        return mark_available(request, item)

    return False
```

---

## Fallback Checker

Runs periodically to catch items that webhooks missed.

### Current Implementation Issues

1. **Bug #2:** Only checks movies (`media_type == "movie"`)
2. **Bug #3:** Single lookup strategy fails for recategorized anime

### Proposed Fallback Checker

```python
async def run_fallback_verification():
    """Check all stuck requests and attempt verification."""

    stmt = select(MediaRequest).where(
        MediaRequest.state.in_([
            RequestState.IMPORTING,
            RequestState.ANIME_MATCHING,
        ]),
        MediaRequest.updated_at < datetime.now() - timedelta(minutes=5),
    )

    requests = await db.execute(stmt)

    for request in requests:
        if request.is_anime:
            # Anime paths (5c, 5d)
            if request.media_type == "movie":
                await verify_anime_movie_fallback(request)
            else:
                await verify_anime_tv_fallback(request)
        else:
            # Regular paths (5a, 5b)
            if request.media_type == "movie":
                await verify_movie_in_jellyfin(request)
            else:
                await verify_tv_in_jellyfin(request)
```

---

## Jellyfin API Reference

### Search by Provider ID

```python
# TMDB (movies and TV)
GET /Items?AnyProviderIdEquals=Tmdb.{tmdb_id}

# TVDB (TV only)
GET /Items?AnyProviderIdEquals=Tvdb.{tvdb_id}

# With type filter
GET /Items?IncludeItemTypes=Movie&AnyProviderIdEquals=Tmdb.{tmdb_id}
GET /Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tvdb.{tvdb_id}
```

### Search by Title

```python
GET /Items?SearchTerm={title}&IncludeItemTypes=Movie,Series
GET /Items?SearchTerm={title}&Years={year}
```

### Response Format

```json
{
  "Items": [
    {
      "Id": "abc123",
      "Name": "Chainsaw Man: The Movie",
      "Type": "Movie",
      "ProviderIds": {
        "Tmdb": "1386807",
        "Imdb": "tt32353804"
      }
    }
  ],
  "TotalRecordCount": 1
}
```

---

## State Summary

| Initial State | Event | Final State |
|---------------|-------|-------------|
| IMPORTING | Jellyfin found (non-anime) | AVAILABLE |
| IMPORTING | Shoko matched (anime, has cross-refs) | AVAILABLE |
| IMPORTING | Shoko matched (anime, no cross-refs) | ANIME_MATCHING |
| ANIME_MATCHING | Fallback found in Jellyfin | AVAILABLE |
| ANIME_MATCHING | Fallback timeout (configurable) | FAILED |

---

## Previous Phase

← [Phase 4: Import](phase-4-import.md)
