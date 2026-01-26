# Per-Episode Tracking Architecture

**Decision Date:** 2026-01-21
**Status:** Approved
**Updated:** 2026-01-22 (with investigation findings)

---

## Overview

TV shows are tracked at the episode level, not just the request level. This enables:
- Fine-grained progress ("8/28 episodes downloaded")
- Identifying stuck episodes
- Handling multi-episode grabs (one hash = multiple episodes)
- Future: Resume from specific episode

Movies remain simple - no Episode rows needed.

---

## Data Model

### MediaRequest (Parent)

```python
class MediaRequest:
    # Core
    id: int
    title: str
    year: int
    media_type: str          # "movie" | "tv"
    state: RequestState      # Aggregate for TV, direct for movies
    is_anime: bool | None

    # Correlation IDs
    jellyseerr_id: int
    tmdb_id: int
    tvdb_id: int | None      # TV only
    imdb_id: str | None

    # Service IDs
    radarr_id: int | None    # Movies
    sonarr_id: int | None    # TV
    jellyfin_id: str | None

    # Movie-specific (not used for TV)
    qbit_hash: str | None    # Single hash for movies
    final_path: str | None   # Import path for movies

    # TV-specific
    requested_seasons: str   # e.g., "1" or "1,2"
    total_episodes: int      # Count of Episode rows

    # Display
    poster_url: str
    requested_by: str
    quality: str | None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    available_at: datetime | None
```

### Episode (TV Only)

```python
class Episode:
    id: int
    request_id: int          # FK → MediaRequest

    # Episode info
    season_number: int
    episode_number: int
    episode_title: str | None  # From Sonarr Grab webhook (no API call needed!)

    # Service IDs
    sonarr_episode_id: int | None  # From Grab webhook episodes[].id
    episode_tvdb_id: int | None    # From Grab webhook episodes[].tvdbId

    # State tracking
    state: EpisodeState      # See states below

    # Correlation
    qbit_hash: str | None    # Set at grab (season packs share same hash)
    final_path: str | None   # Set at import
    shoko_file_id: str | None  # Set at Shoko match (anime only)
    jellyfin_id: str | None  # Set at verification

    # Timestamps
    created_at: datetime
    updated_at: datetime

    # Note: download_progress is NOT stored - derived from qBit hash lookup at runtime
```

---

## Episode States

```
PENDING      ← Created from Sonarr API, not grabbed yet
GRABBING     ← Sonarr grabbed, qBit queued/starting
DOWNLOADING  ← qBit actively downloading
DOWNLOADED   ← qBit complete, waiting for import
IMPORTING    ← Sonarr importing to library
AVAILABLE    ← In Jellyfin, ready to watch
FAILED       ← Error occurred
```

**State Flow:**
```
PENDING → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE
                                                    ↓
                                              (anime only)
                                            ANIME_MATCHING
                                                    ↓
                                               AVAILABLE
```

---

## Request State Aggregation

For TV shows, `MediaRequest.state` is derived from episode states:

```python
def calculate_request_state(episodes: list[Episode]) -> RequestState:
    """Derive request state from episode states."""
    states = [e.state for e in episodes]

    # All complete
    if all(s == EpisodeState.AVAILABLE for s in states):
        return RequestState.AVAILABLE

    # Any failed
    if any(s == EpisodeState.FAILED for s in states):
        return RequestState.FAILED

    # Priority order for in-progress states
    if any(s == EpisodeState.IMPORTING for s in states):
        return RequestState.IMPORTING
    if any(s == EpisodeState.DOWNLOADED for s in states):
        return RequestState.DOWNLOAD_DONE
    if any(s == EpisodeState.DOWNLOADING for s in states):
        return RequestState.DOWNLOADING
    if any(s == EpisodeState.GRABBING for s in states):
        return RequestState.GRABBING

    return RequestState.APPROVED
```

---

## Phase-by-Phase Changes

### Phase 1: Request Creation

**Movies:** No change - create MediaRequest only.

**TV:** Create MediaRequest with `requested_seasons`. Episode rows created in Phase 2.

### Phase 2: Indexer Grab

**Movies:** Store `qbit_hash` on MediaRequest, transition to GRABBING.

**TV:**
1. Sonarr Grab webhook includes **full episode list with titles and tvdbIds** - no API call needed!
2. Create Episode rows directly from webhook `episodes[]` array
3. All episodes share the same `qbit_hash` for season packs
4. Detect `is_anime` from `series.type == "anime"`

```python
# Sonarr Grab webhook has everything we need!
# payload["episodes"] = [
#   {"id": 739, "episodeNumber": 1, "seasonNumber": 1, "title": "Easy does it", "tvdbId": 8916235},
#   {"id": 740, "episodeNumber": 2, "seasonNumber": 1, "title": "The more the merrier", "tvdbId": 9234918},
#   ... (all episodes in this grab)
# ]

download_id = payload["downloadId"]  # qBit hash (40-char hex)

# Create Episode rows directly from webhook
for ep in payload["episodes"]:
    await create_episode(
        request_id=request.id,
        sonarr_episode_id=ep["id"],
        season_number=ep["seasonNumber"],
        episode_number=ep["episodeNumber"],
        episode_title=ep["title"],       # Available in webhook!
        episode_tvdb_id=ep.get("tvdbId"),
        qbit_hash=download_id,           # Same hash for all (season pack)
        state=EpisodeState.GRABBING
    )

request.total_episodes = len(payload["episodes"])
request.is_anime = payload["series"]["type"] == "anime"
```

**Key discovery:** No Sonarr API call needed - the Grab webhook contains the complete episode list with titles and tvdbIds.

### Phase 3: Download Progress

**Movies:** Track single `qbit_hash`, update `download_progress`.

**TV:**
1. Get all unique hashes from Episode table for active requests
2. Poll qBit for those hashes
3. Update Episode states based on torrent progress

```python
# Get episodes by hash
episodes = await get_episodes_by_hash(db, torrent_hash)

for episode in episodes:
    if torrent.progress >= 1.0:
        episode.state = EpisodeState.DOWNLOADED
    elif torrent.progress > 0:
        episode.state = EpisodeState.DOWNLOADING

# Recalculate request state
request.state = calculate_request_state(await get_all_episodes(db, request.id))
```

### Phase 4: Import

**Movies:** Store `final_path` on MediaRequest, transition to IMPORTING.

**TV:**
1. Season pack = **ONE webhook** with `episodeFiles[]` (plural) containing all file paths
2. Individual episodes = one webhook per episode with `episodeFile` (singular)
3. Match episodes by `seasonNumber` + `episodeNumber`

```python
# Season pack format (ONE webhook for all 13 episodes):
# payload["episodes"] = [{...}, {...}, ...] (all 13)
# payload["episodeFiles"] = [
#   {"relativePath": "Season 1/S01E01.mkv", "path": "/data/anime/shows/.../S01E01.mkv"},
#   {"relativePath": "Season 1/S01E02.mkv", "path": "/data/anime/shows/.../S01E02.mkv"},
#   ... (all 13 files)
# ]

# Check for season pack (plural) vs single episode (singular)
episode_files = payload.get("episodeFiles", [])  # Season pack
if not episode_files:
    episode_file = payload.get("episodeFile")    # Single episode
    if episode_file:
        episode_files = [episode_file]

# Update each episode with its final path
for i, ep in enumerate(payload["episodes"]):
    file_path = episode_files[i]["path"] if i < len(episode_files) else None
    await update_episode(
        request_id=request.id,
        season_number=ep["seasonNumber"],
        episode_number=ep["episodeNumber"],
        final_path=file_path,
        state=EpisodeState.IMPORTING
    )
```

### Phase 5: Verification

**Movies:** Jellyfin TMDB lookup, transition to AVAILABLE.

**TV:**
- Option A: Check if all episodes exist in Jellyfin (per-episode verification)
- Option B: Check if series/season exists (aggregate verification)

```python
# Per-episode verification
for episode in episodes:
    jellyfin_ep = await jellyfin_client.find_episode(
        series_tvdb_id=request.tvdb_id,
        season=episode.season_number,
        episode=episode.episode_number
    )
    if jellyfin_ep:
        episode.state = EpisodeState.AVAILABLE
        episode.jellyfin_id = jellyfin_ep["Id"]

# Update request state
request.state = calculate_request_state(episodes)
```

---

## Season Pack Handling (Captured 2026-01-21)

When Sonarr grabs a season pack, all episodes share the same `downloadId`:

```json
{
  "eventType": "Grab",
  "series": {
    "id": 23,
    "title": "Lycoris Recoil",
    "tvdbId": 414057,
    "type": "anime"
  },
  "episodes": [
    {"id": 739, "episodeNumber": 1, "seasonNumber": 1, "title": "Easy does it", "tvdbId": 8916235},
    {"id": 740, "episodeNumber": 2, "seasonNumber": 1, "title": "The more the merrier", "tvdbId": 9234918},
    "... (all 13 episodes)"
  ],
  "downloadId": "3F92992E2FBEB6EBB251304236BF5E0B600A91C3"
}
```

All 13 episodes get the same `qbit_hash`. When that torrent completes, all episodes transition to DOWNLOADED together.

**Individual episode grabs:** If Sonarr grabs episodes individually (not a season pack), each Grab webhook creates Episode rows with different hashes.

**Why this doesn't matter for our architecture:** We store `qbit_hash` per Episode row, not per Request. When qBit reports progress for a hash, we update ALL episodes with that hash. Works the same whether it's a season pack (all same hash) or individual grabs (different hashes).

---

## Display Examples

### Request List View
```
Frieren: Beyond Journey's End (2023)
Season 1 • DOWNLOADING • 8/28 episodes
[████████░░░░░░░░░░░░] 29%
```

### Request Detail View
```
Frieren: Beyond Journey's End
Season 1 • 8 of 28 episodes downloaded

Episode 1  "The Journey's End"        ✓ Available
Episode 2  "It Didn't Have to Be..."  ✓ Available
Episode 3  "Killing Magic"            ✓ Available
...
Episode 8  "Frieren the Slayer"       ✓ Available
Episode 9  "Aura the Guillotine"      ⬇ Downloading (67%)
Episode 10 "A Replica That Surpasses" ⬇ Downloading (67%)  ← same hash
Episode 11 "Winter in Norte"          ⏳ Grabbed
Episode 12 "A Real Hero"              ○ Pending
...
```

---

## Investigation Findings (2026-01-21)

- [x] **Sonarr Grab webhook** - Full `episodes[]` array with titles and tvdbIds. **No API call needed!**
- [x] **Sonarr Import webhook** - Season pack sends ONE webhook with `episodeFiles[]` (plural) containing all file paths
- [x] **is_anime detection** - `series.type == "anime"` (Sonarr), `movie.tags` contains "anime" (Radarr)
- [x] **downloadId format** - 40-character uppercase hex (SHA1 hash) matching qBit hash exactly

See `captured-webhooks/sonarr-grab.json` and `captured-webhooks/sonarr-import.json` for full payloads.

---

## Decisions Made

| Question | Decision |
|----------|----------|
| Episode rows for TV? | Yes |
| Episode rows for movies? | No - movies stay simple |
| When create Episode rows? | Phase 2 - directly from Grab webhook (no API call) |
| Episode info source? | Grab webhook `episodes[]` has titles and tvdbIds |
| Season pack handling? | All episodes share same `qbit_hash` |
| Multi-season request? | Only track requested season(s) |
| Episode state vs Request state? | Episode has own state, Request state is aggregate |
| is_anime detection? | Phase 2 from `series.type` / `movie.tags` |
