# Webhook Capture Findings

**Date:** 2026-01-21
**Test requests:** Violet Evergarden: The Movie, Violet Evergarden: Recollections, Lycoris Recoil

---

## Key Findings

### 1. Anime Detection

**Radarr:** Use `movie.tags` array - contains `"anime"` if tagged
**Sonarr:** Use `series.type` field - value is `"anime"` for anime series

Both also have:
- `originalLanguage.name` = "Japanese"
- `release.indexer` contains "Nyaa"

### 2. No Japanese Title in Webhooks

Neither Radarr nor Sonarr include `originalTitle` in Grab webhooks.
**Alternative sources needed:**
- TMDB API (has `original_title` field)
- AniDB via Shoko

### 3. Jellyseerr Never Sends "special"

Violet Evergarden: Recollections (a recap movie) was sent as `media_type: "movie"`.
Jellyseerr only sends `"movie"` or `"tv"`.

### 4. Sonarr Grab Includes Full Episode List

Season pack grab includes ALL episodes in `episodes[]` array:
- `id` - Sonarr internal ID
- `episodeNumber`, `seasonNumber`
- `title` - Episode title
- `tvdbId` - Per-episode TVDB ID

**This answers Q3 (Phase 2):** No need to call Sonarr API - episode list comes in Grab webhook!

### 5. Single Hash for Season Pack

Season pack download = single `downloadId` for all 13 episodes.
All Episode rows will share the same `qbit_hash`.

---

## Field Mapping

### Jellyseerr → MediaRequest

| Webhook Field | DB Field |
|---------------|----------|
| `subject` | `title` (parse year out) |
| `media.media_type` | `media_type` |
| `media.tmdbId` | `tmdb_id` |
| `media.tvdbId` | `tvdb_id` |
| `request.request_id` | `jellyseerr_id` |
| `request.requestedBy_username` | `requested_by` |
| `image` | `poster_url` |
| `extra[name="Requested Seasons"].value` | `requested_seasons` |

### Radarr Grab → MediaRequest (Movie)

| Webhook Field | DB Field |
|---------------|----------|
| `movie.id` | `radarr_id` |
| `movie.tmdbId` | `tmdb_id` (verify) |
| `movie.imdbId` | `imdb_id` |
| `movie.year` | `year` |
| `movie.folderPath` | `final_path` (partial) |
| `movie.tags` | Check for "anime" → `is_anime` |
| `release.quality` | `quality` |
| `release.indexer` | `indexer` |
| `release.size` | `file_size` |
| `downloadId` | `qbit_hash` |

### Sonarr Grab → MediaRequest + Episodes (TV)

| Webhook Field | DB Field |
|---------------|----------|
| `series.id` | `sonarr_id` |
| `series.tvdbId` | `tvdb_id` (verify) |
| `series.tmdbId` | `tmdb_id` |
| `series.imdbId` | `imdb_id` |
| `series.year` | `year` |
| `series.path` | `final_path` (series folder) |
| `series.type` | Check for "anime" → `is_anime` |
| `release.quality` | `quality` |
| `release.indexer` | `indexer` |
| `release.size` | `file_size` |
| `downloadId` | shared `qbit_hash` for all episodes |
| `episodes[]` | Create Episode rows |

### Sonarr episodes[] → Episode Rows

| Webhook Field | DB Field |
|---------------|----------|
| `episodes[].id` | (Sonarr internal, don't store) |
| `episodes[].seasonNumber` | `season_number` |
| `episodes[].episodeNumber` | `episode_number` |
| `episodes[].title` | `episode_title` |
| `episodes[].tvdbId` | (optional, for debugging) |

### Radarr Import (Download) → MediaRequest (Movie)

| Webhook Field | DB Field |
|---------------|----------|
| `movieFile.path` | `final_path` ← **CRITICAL for Shoko** |
| `downloadId` | `qbit_hash` (verify match) |
| `movie.id` | `radarr_id` (verify match) |

**Note:** Import webhook has full file path, Grab only has folder path.

### Sonarr Import (Download) → Episode Rows (TV)

| Webhook Field | DB Field |
|---------------|----------|
| `episodeFiles[].path` | `Episode.final_path` |
| `downloadId` | `qbit_hash` (verify match) |
| `series.id` | `sonarr_id` (verify match) |

**Season pack vs per-episode:** Webhook structure is identical - `episodeFiles[]` array either way. For season pack, all episodes in one webhook. For per-episode grabs, one episode per webhook. Just iterate and update Episode rows.

### Shoko SignalR Events

Shoko uses SignalR, not webhooks. Events observed:
- `ShokoEvent:FileDetected` - file found
- `ShokoEvent:FileHashed` - file hashed
- `ShokoEvent:FileMatched` - file matched to AniDB
- `ShokoEvent:SeriesUpdated` - series metadata updated
- `ShokoEvent:EpisodeUpdated` - per-episode updates (many for TV)

**FileMatched payload:** Has `cross-refs` boolean - if `False`, file not yet matched to AniDB series.

---

## Questions Answered

### Phase 1 - Q2: media_type "special"

**Answer:** Jellyseerr never sends "special". Remove from schema, use only `movie | tv`.

### Phase 2 - Q1: title_japanese / originalTitle

**Answer:** Not in webhook. Must fetch from TMDB API or skip for MVP.

### Phase 2 - Q3: How do we know total_episodes?

**Answer:** Sonarr Grab webhook includes full `episodes[]` array! No API call needed.

---

## Capture Status

- [x] Jellyseerr MEDIA_AUTO_APPROVED (movie + TV)
- [x] Radarr Grab
- [x] Sonarr Grab (season pack with episodes[])
- [x] Radarr Import (Download)
- [x] Sonarr Import (Download) - season pack with episodeFiles[]
- [x] Shoko SignalR events (FileDetected, FileHashed, FileMatched, SeriesUpdated, EpisodeUpdated)
- [ ] Jellyfin ItemAdded webhook (optional - using fallback checker instead)
