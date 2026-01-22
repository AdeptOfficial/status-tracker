# Phase 2: Indexer Grab

**Source:** Radarr (movies) or Sonarr (TV)
**Trigger:** Webhook `eventType: "Grab"`
**State Transition:**
- Movies: `APPROVED` → `GRABBING`
- TV: `APPROVED` → `GRABBING`

---

## Overview

When Radarr/Sonarr finds a release on an indexer and sends it to qBittorrent, they fire a Grab webhook. This is where we:
1. Get the **downloadId** (qBit hash - 40-char uppercase hex)
2. Detect **is_anime** from `series.type` or `movie.tags`
3. Create **Episode rows** for TV (all episode info is in the webhook!)

**Key discovery:** Sonarr Grab webhook includes the full `episodes[]` array with titles and tvdbIds. No API call needed!

**Season Pack Handling:** For season packs, all episodes share the same `downloadId`. The `episodes[]` array tells us exactly which episodes are being grabbed.

---

## Webhook Payloads (Captured 2026-01-21)

### Radarr Grab (Movie)

```json
{
  "eventType": "Grab",
  "movie": {
    "id": 52,
    "title": "Violet Evergarden: The Movie",
    "year": 2020,
    "folderPath": "/data/anime/movies/Violet Evergarden - The Movie (2020)",
    "tmdbId": 533514,
    "imdbId": "tt8652818",
    "tags": ["anime"]
  },
  "release": {
    "quality": "Bluray-1080p",
    "releaseTitle": "[The-Nut] Violet Evergarden The Movie 2020 [BD][1080p 10bit AV1]",
    "indexer": "Nyaa.si (Prowlarr)",
    "size": 1181116032
  },
  "downloadClient": "qBittorrent (VPN)",
  "downloadId": "C2C60F66C126652A86F7F2EE73DC83D4E255929E"
}
```

**is_anime detection:** `movie.tags` contains `"anime"`

### Sonarr Grab (TV - Season Pack)

```json
{
  "eventType": "Grab",
  "series": {
    "id": 23,
    "title": "Lycoris Recoil",
    "path": "/data/anime/shows/Lycoris Recoil",
    "tvdbId": 414057,
    "tmdbId": 154494,
    "imdbId": "tt16755706",
    "type": "anime"
  },
  "episodes": [
    {"id": 739, "episodeNumber": 1, "seasonNumber": 1, "title": "Easy does it", "tvdbId": 8916235},
    {"id": 740, "episodeNumber": 2, "seasonNumber": 1, "title": "The more the merrier", "tvdbId": 9234918},
    "... (all 13 episodes with titles and tvdbIds)"
  ],
  "release": {
    "quality": "Bluray-1080p",
    "releaseTitle": "[FLE] Lycoris Recoil - S01 REPACK (BD 1080p HEVC x265 Opus) [Dual Audio]",
    "indexer": "Nyaa.si (Prowlarr)",
    "size": 33930242048
  },
  "downloadClient": "qBittorrent (VPN)",
  "downloadId": "3F92992E2FBEB6EBB251304236BF5E0B600A91C3"
}
```

**is_anime detection:** `series.type == "anime"`

**Episode data available at Grab time:**
- `id` - Sonarr internal ID
- `episodeNumber` / `seasonNumber`
- `title` - Episode title (no API call needed!)
- `tvdbId` - Per-episode TVDB ID

**Season pack:** All episodes share the same `downloadId` (qBit hash)

---

## Field Extraction

### Request-Level Fields

| Field | Radarr Source | Sonarr Source | Required | Notes |
|-------|---------------|---------------|----------|-------|
| `qbit_hash` | `downloadId` | `downloadId` | **CRITICAL** | 40-char uppercase hex |
| `is_anime` | `movie.tags` contains "anime" | `series.type == "anime"` | YES | Early detection |
| `arr_id` | `movie.id` | `series.id` | YES | For deletion sync |
| `tmdb_id` | `movie.tmdbId` | `series.tmdbId` | YES | Correlation |
| `tvdb_id` | N/A | `series.tvdbId` | TV only | Correlation |
| `imdb_id` | `movie.imdbId` | `series.imdbId` | NO | Library sync |
| `quality` | `release.quality` | `release.quality` | NO | Display |
| `indexer` | `release.indexer` | `release.indexer` | NO | Display |
| `file_size` | `release.size` | `release.size` | NO | Display |

### Episode-Level Fields (TV Only)

| Field | Source | Required | Notes |
|-------|--------|----------|-------|
| `sonarr_episode_id` | `episodes[].id` | YES | Sonarr internal ID |
| `season_number` | `episodes[].seasonNumber` | YES | |
| `episode_number` | `episodes[].episodeNumber` | YES | |
| `episode_title` | `episodes[].title` | YES | No API call needed! |
| `episode_tvdb_id` | `episodes[].tvdbId` | NO | Per-episode TVDB ID |
| `qbit_hash` | Inherited from request | YES | Season packs share hash |
| `state` | N/A | YES | Initial: GRABBING |

---

## Flow

### Movies

```
Radarr Grab webhook
        │
        ▼
┌─────────────────────────────────┐
│ Find request by tmdb_id         │
│ (exclude AVAILABLE, DELETED)    │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│ Detect is_anime:                │
│ "anime" in movie.tags           │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│ Store on request:               │
│ - qbit_hash = downloadId        │
│ - radarr_id = movie.id          │
│ - is_anime                      │
│ - quality, indexer, file_size   │
│ state → GRABBING                │
└─────────────────────────────────┘
```

### TV Shows (Per-Episode Model)

```
Sonarr Grab webhook
        │
        ▼
┌─────────────────────────────────┐
│ Find request by tvdb_id         │
│ (exclude AVAILABLE, DELETED)    │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│ Detect is_anime:                │
│ series.type == "anime"          │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│ Store on request:               │
│ - qbit_hash = downloadId        │
│ - sonarr_id = series.id         │
│ - is_anime                      │
│ - quality, indexer, file_size   │
│ state → GRABBING                │
└─────────────────────────────────┘
        │
        ▼
┌─────────────────────────────────┐
│ For each episode in episodes[]: │
│ CREATE Episode row:             │
│ - season_number                 │
│ - episode_number                │
│ - episode_title (from webhook!) │
│ - episode_tvdb_id               │
│ - qbit_hash (same for all)      │
│ - state = GRABBING              │
└─────────────────────────────────┘
```

**Key insight:** Season pack episodes all share the same `downloadId`. We create all Episode rows upfront with the episode titles from the webhook - no Sonarr API call needed!

---

## Implementation Notes

### is_anime Detection

Detect at Phase 2 (earliest possible):

```python
def detect_is_anime_radarr(payload: dict) -> bool:
    """Detect anime from Radarr Grab payload."""
    tags = payload.get("movie", {}).get("tags", [])
    return "anime" in tags

def detect_is_anime_sonarr(payload: dict) -> bool:
    """Detect anime from Sonarr Grab payload."""
    series_type = payload.get("series", {}).get("type", "")
    return series_type == "anime"
```

### Creating Episode Rows

At Grab time, create Episode rows from webhook data:

```python
async def create_episode_rows(request: MediaRequest, payload: dict, db: AsyncSession):
    """Create Episode rows from Sonarr Grab webhook."""
    download_id = payload.get("downloadId")
    episodes_data = payload.get("episodes", [])

    for ep in episodes_data:
        episode = Episode(
            request_id=request.id,
            sonarr_episode_id=ep.get("id"),
            season_number=ep.get("seasonNumber"),
            episode_number=ep.get("episodeNumber"),
            episode_title=ep.get("title"),  # Available in webhook!
            episode_tvdb_id=ep.get("tvdbId"),
            qbit_hash=download_id,  # All share same hash for season packs
            state=EpisodeState.GRABBING,
        )
        db.add(episode)
```

### Multiple Grabs (Individual Episodes)

If Sonarr grabs episodes individually (not a season pack), each Grab webhook creates Episode rows with different hashes:

```python
# Grab 1: Episodes 1-2 with hash "AAA..."
# Grab 2: Episodes 3-4 with hash "BBB..."
# Each episode row has its own qbit_hash for download tracking
```

---

## State Transitions

### Movies
```
APPROVED → GRABBING
```

### TV Shows (Request Level)
```
APPROVED → GRABBING
```

### TV Shows (Episode Level)
```
Episode created at GRABBING
```

**Note:** The request stays in GRABBING until qBit reports download activity. Phase 3 (Download Progress) transitions both request and episodes to DOWNLOADING.

---

## Season Pack Detection (Optional)

Season packs can be detected by checking the release title, but this is **informational only** - we always create Episode rows for whatever episodes are in the `episodes[]` array.

```python
import re

def is_season_pack(payload: dict) -> bool:
    """Check if this grab is a full season pack (informational)."""
    release_title = payload.get("release", {}).get("releaseTitle", "")

    patterns = [
        r"S\d{2}(?!E)",      # S01 without E## following
        r"Season\s*\d+",     # Season 1, Season01
        r"Complete",         # Complete Series/Season
        r"BATCH",            # Batch release
    ]

    return any(re.search(p, release_title, re.IGNORECASE) for p in patterns)
```

**Note:** We no longer need to query Sonarr API for episode count - the `episodes[]` array tells us exactly what's being grabbed.

---

## Data Stored After Phase 2

### Movie
```python
request.qbit_hash = "C2C60F66C126652A86F7F2EE73DC83D4E255929E"
request.radarr_id = 52
request.is_anime = True  # Detected from movie.tags
request.quality = "Bluray-1080p"
request.indexer = "Nyaa.si (Prowlarr)"
request.file_size = 1181116032
request.state = RequestState.GRABBING
```

### TV Show (Request)
```python
request.qbit_hash = "3F92992E2FBEB6EBB251304236BF5E0B600A91C3"
request.sonarr_id = 23
request.is_anime = True  # Detected from series.type
request.quality = "Bluray-1080p"
request.indexer = "Nyaa.si (Prowlarr)"
request.file_size = 33930242048
request.state = RequestState.GRABBING
```

### TV Show (Episodes)
```python
# 13 Episode rows created:
Episode(
    request_id=request.id,
    sonarr_episode_id=739,
    season_number=1,
    episode_number=1,
    episode_title="Easy does it",
    episode_tvdb_id=8916235,
    qbit_hash="3F92992E2FBEB6EBB251304236BF5E0B600A91C3",  # Same as request
    state=EpisodeState.GRABBING,
)
# ... (12 more episodes)
```

---

## Correlation Strategy

**Grab webhook (Phase 2):**
1. Find by `tmdb_id` (movie) or `tvdb_id` (TV)
2. Exclude `AVAILABLE` and `DELETED` states
3. Order by `created_at DESC` (most recent request)
4. Store hash on request (and Episode rows for TV)

**Later webhooks (Phase 3+):**
1. Find request/episode by `qbit_hash`
2. Movies: lookup by request.qbit_hash
3. TV: lookup by episode.qbit_hash (then get parent request)

---

## Testing Checklist

- [ ] Radarr Grab creates GRABBING state for movie
- [ ] Sonarr Grab creates GRABBING state for TV request
- [ ] Episode rows created for all episodes in `episodes[]`
- [ ] `is_anime` detected from `movie.tags` or `series.type`
- [ ] Correct request matched (not old AVAILABLE one)
- [ ] Season pack: all episodes have same `qbit_hash`
- [ ] Individual grabs: each batch has its own `qbit_hash`

---

## Previous Phase

← [Phase 1: Request Creation](phase-1-request-creation.md)

## Next Phase

→ [Phase 3: Download Progress](phase-3-download-progress.md)
