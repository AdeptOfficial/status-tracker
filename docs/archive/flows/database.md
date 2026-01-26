# Database Schema

## Design Principles

1. **Correlation first** - Every ID field exists to match webhooks to requests
2. **Bigger picture** - Schema supports request flow, library sync, AND deletion
3. **Don't duplicate** - If it's in the title string, don't store separately

---

## Core Fields

```
id
title                ← Display name from Jellyseerr (includes year usually)
media_type           ← "movie" | "tv" (Jellyseerr never sends "special")
is_anime             ← Determines verification path, detected at Phase 2
state                ← Current state in flow (see States below)
year                 ← For disambiguation in searches
```

**Note on is_anime detection (Phase 2):**
- Radarr: `movie.tags` contains `"anime"`
- Sonarr: `series.type == "anime"`

**Deferred to post-MVP:** `title_japanese` - not in webhooks, requires TMDB API call.

---

## States (9 Total)

```
REQUESTED      ← User requested, awaiting admin approval
APPROVED       ← Approved, waiting for Radarr/Sonarr to grab
GRABBING       ← Grabbed, qBit queued/starting (shows "Grabbed 3/12 eps" for TV)
DOWNLOADING    ← qBit downloading
DOWNLOADED     ← qBit complete, waiting for Radarr/Sonarr import
IMPORTING      ← Radarr/Sonarr importing to library
ANIME_MATCHING ← Anime only: waiting for Shoko to match
AVAILABLE      ← In Jellyfin, ready to watch
FAILED         ← Error occurred
```

**State Flow:**

```
REQUESTED → APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE
                                                                 │
                                                          (anime only)
                                                                 ↓
                                                          ANIME_MATCHING
                                                                 ↓
                                                            AVAILABLE
```

**Notes:**
- Movies: Same flow (GRABBING just means "grabbed 1 file")
- TV: GRABBING shows episode progress ("Grabbed 3/12 eps")
- DOWNLOADED helps debug stuck imports (qBit done but Radarr/Sonarr hasn't imported)
- ANIME_MATCHING only for anime content waiting on Shoko
- Any state can transition to FAILED on error

---

## Correlation IDs (Primary Purpose: Match Webhooks)

| Field | Set At | Used For |
|-------|--------|----------|
| `jellyseerr_id` | Phase 1 | Jellyseerr webhook correlation |
| `tmdb_id` | Phase 1 | Movies, Jellyfin lookup, library sync |
| `tvdb_id` | Phase 1 | TV, Jellyfin lookup, library sync |
| `imdb_id` | Phase 2 | Library sync, deletion (cross-platform) |
| `qbit_hash` | Phase 2 | Download tracking (see note below) |
| `final_path` | Phase 4 | Shoko FileMatched correlation (CRITICAL) |

**qbit_hash storage:**
- **Movies:** `MediaRequest.qbit_hash` (single string)
- **TV:** `Episode.qbit_hash` on each Episode row
  - Season pack: All episodes share same hash
  - Individual grabs: Each episode has its own hash

**Correlation:** For TV, query Episode table by hash, join to MediaRequest.

---

## Service IDs (Primary Purpose: Deletion & Sync)

```
radarr_id            ← For deletion sync (movies)
sonarr_id            ← For deletion sync (TV)
jellyfin_id          ← Library sync matching, "View in Jellyfin" link
shoko_file_id        ← Trigger file missing sync in Shoko (anime only)
```

---

## Progress Tracking (Movies)

```
download_progress    ← 0-100, updated during Phase 3
```

## Episode Table (TV Only)

Sonarr Grab webhook includes full `episodes[]` array - no API call needed!

```
Episode:
  id
  request_id           ← FK to MediaRequest
  season_number        ← From Sonarr Grab episodes[].seasonNumber
  episode_number       ← From Sonarr Grab episodes[].episodeNumber
  episode_title        ← From Sonarr Grab episodes[].title
  state                ← PENDING | GRABBING | DOWNLOADING | DOWNLOADED | IMPORTING | AVAILABLE
  qbit_hash            ← Shared across all eps in season pack
  final_path           ← Set at Import
  shoko_file_id        ← Anime only
  jellyfin_id          ← Per-episode verification
  created_at
  updated_at
```

**Season pack:** All episodes share same `qbit_hash` (single download)

**TV Progress Display:** Count Episode rows by state:
- GRABBING: "Grabbed 3/12 eps" → `count(state >= GRABBING)`
- DOWNLOADING: "3 downloaded, 5 downloading" → count by state
- AVAILABLE: "Available"

**Live updates:** qBit poller writes to DB → broadcasts via WebSocket → frontend updates.

---

## Display / Metadata

```
poster_url           ← From Jellyseerr `image` field
requested_by         ← Username
quality              ← "Bluray-1080p" (from Radarr/Sonarr Grab)
indexer              ← "Nyaa" etc (nice-to-have)
requested_seasons    ← TV only, which season(s) requested
file_size            ← Bytes, for admin storage tracking (from Grab)
```

---

## Timestamps

```
created_at           ← Request created
updated_at           ← Last state change
available_at         ← When reached AVAILABLE (for metrics)

```

---

## What We're NOT Storing (MVP)

| Field | Why Skip |
|-------|----------|
| `title_japanese` | Not in webhooks, requires TMDB API call (post-MVP) |
| `anidb_id` | Shoko uses it internally, but we correlate via `final_path` |
| `download_eta` | Too transient, changes every poll, clutters DB |
| `release_title` | Long string, only useful for debugging |

---

## Field Sources by Phase

| Phase | MediaRequest Fields | Episode Fields (TV) |
|-------|---------------------|---------------------|
| 1 - Jellyseerr | title, media_type, tmdb_id, tvdb_id, jellyseerr_id, poster_url, requested_by, year, requested_seasons | - |
| 2 - Grab | qbit_hash, radarr_id/sonarr_id, quality, imdb_id, indexer, file_size, **is_anime** | Create all rows: season_number, episode_number, episode_title, qbit_hash, state=GRABBING |
| 3 - Download | download_progress (movies) | Update state: DOWNLOADING → DOWNLOADED |
| 4 - Import | final_path | final_path, shoko_file_id (anime) |
| 5 - Verify | jellyfin_id, available_at | jellyfin_id, state=AVAILABLE |

**Key change:** `is_anime` detected at Phase 2 from `movie.tags` or `series.type`, not Phase 4.
