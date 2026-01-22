# Investigation Findings - 2026-01-21

## Test Requests Made

1. **Violet Evergarden: The Movie (2020)** - anime movie
2. **Violet Evergarden: Recollections (2021)** - special/recap movie
3. **Lycoris Recoil (2022)** - TV anime

---

## Key Findings

### 1. Jellyseerr Payload Differences (Movie vs TV)

| Field | Movie | TV |
|-------|-------|-----|
| `media.media_type` | `"movie"` | `"tv"` |
| `media.tvdbId` | `""` (empty) | `"414057"` |
| `extra` | `[]` | `[{"name": "Requested Seasons", "value": "1"}]` |

**Conclusion:** Use `media.media_type` to distinguish, and `media.tvdbId` for TV correlation.

### 2. Requested Seasons Format

```json
"extra": [
  {
    "name": "Requested Seasons",
    "value": "1"
  }
]
```

- Single season: `"value": "1"`
- **TODO:** Test multi-season request to see format (likely `"1, 2"` or `"1,2"`)

### 3. Radarr `downloadId` = qBit Hash

**CONFIRMED:** The `downloadId` field from Radarr Grab webhook is the qBittorrent hash.

```
downloadId: "C2C60F66C126652A86F7F2EE73DC83D4E255929E"
```

- 40 character uppercase hex string (SHA1 hash)
- Matches qBit's `hash` field exactly
- **Answers Phase 3 Q6 ✓**

### 4. Specials Are Movies

Violet Evergarden: Recollections (2021) - a "special" recap movie:
- Handled by **Radarr**, not Sonarr
- `media_type: "movie"` from Jellyseerr
- No special `media_type: "special"` flag

**Conclusion:** Specials that are standalone are treated as movies. Episode specials (S00E01) would go through Sonarr.

### 5. Sonarr Grab Webhook (TV/Season Pack)

**RECEIVED:** Sonarr sent Grab webhook for Lycoris Recoil (arrived ~3 min after Jellyseerr).

Key fields:
```
series.id         - Sonarr internal ID (23)
series.title      - "Lycoris Recoil"
series.tvdbId     - 414057 (matches Jellyseerr!)
series.type       - "anime" (anime flag!)
series.path       - "/data/anime/shows/Lycoris Recoil"

episodes[]        - Array of ALL episodes in this grab
  .episodeNumber  - 1, 2, 3...
  .seasonNumber   - 1
  .title          - "Easy does it", "The more the merrier"...
  .tvdbId         - Per-episode TVDB ID

release.size      - 33930242048 (~33GB season pack)
release.releaseTitle - "[FLE] Lycoris Recoil - S01 REPACK..."

downloadId        - "3F92992E2FBEB6EBB251304236BF5E0B600A91C3"
```

**Key insight for per-episode tracking:** The `episodes[]` array tells us exactly which episodes are in this grab. For a season pack, all 12-13 episodes share the same `downloadId` (qBit hash).

### 6. Radarr Payload Structure

Key fields available:
```
movie.id          - Radarr internal ID
movie.title       - Title
movie.year        - Year
movie.tmdbId      - TMDB ID (for correlation)
movie.imdbId      - IMDB ID
movie.folderPath  - Final destination path
movie.tags        - ["anime"] for anime content

release.quality   - "Bluray-1080p"
release.size      - File size in bytes
release.releaseTitle - Full torrent name

downloadId        - qBit hash
downloadClient    - "qBittorrent (VPN)"
```

### 7. Radarr Import (eventType: "Download")

**CAPTURED:** Radarr Import webhook for Violet Evergarden: Recollections.

Key fields:
```
eventType           - "Download" (confusing name, means import)
movie.tags          - ["anime"] (confirms is_anime at import time)
movieFile.path      - "/data/anime/movies/Violet Evergarden - Recollections (2021)/..."
movieFile.quality   - "WEBDL-1080p"
movieFile.size      - 3725336767
downloadId          - "327CCE10156316F79C005B0E953B9E8498E066EB" (same as grab)
sourcePath          - Original download location
destinationPath     - Final library location (same as movieFile.path)
```

### 8. Shoko SignalR Events (How Shoko Notifies Us)

**ANSWERED:** Shoko uses SignalR hub connection, NOT webhooks.

```
Hub URL: http://shoko:8111/signalr/aggregate?feeds=shoko,file
```

**Event sequence observed:**
```
22:36:40 - ShokoEvent:FileDetected   (file seen)
22:36:58 - ShokoEvent:FileHashed     (hash computed, ~18s)
22:36:59 - ShokoEvent:FileMatched    (matched to AniDB) ← KEY EVENT
22:36:59 - ShokoEvent:SeriesUpdated  (metadata updated)
```

**FileMatched** is the important one - triggers `importing → anime_matching` transition.

### 9. State Transitions Observed (Full Flow)

```
Jellyseerr MEDIA_AUTO_APPROVED → creates request (state: approved)
Radarr Grab                    → approved → indexed
qBit poll                      → indexed → downloading → download_done
Radarr Import                  → download_done → importing
Shoko FileMatched              → importing → anime_matching
(Fallback/Jellyfin)            → anime_matching → available
```

Full anime movie flow working.

---

## Investigation Items Updated

### Answered

- [x] **Q6: qBit hash format** - `downloadId` from Radarr/Sonarr IS the qBit hash (40-char uppercase hex)
- [x] **Does Jellyseerr send `media_type: "special"`?** - No, specials are movies
- [x] **How does Shoko notify us?** - SignalR hub at `shoko:8111/signalr/aggregate`, `ShokoEvent:FileMatched` is key event
- [x] **is_anime detection** - `movie.tags` contains `"anime"` (Radarr), `series.type == "anime"` (Sonarr)

### 10. Sonarr Import (Season Pack)

**CAPTURED:** Sonarr sends ONE webhook with ALL episode files for season packs!

Key structure:
```
eventType       - "Download"
series.type     - "anime"
episodes[]      - All 13 episodes
episodeFiles[]  - All 13 file paths (NOT episodeFile singular!)
sourcePath      - Download folder
destinationPath - Season folder
downloadId      - Same hash as grab
```

**Important:** Season pack = `episodeFiles[]` (plural), individual eps = `episodeFile` (singular).

### 11. Shoko TV Events (EpisodeUpdated)

For TV series, Shoko sends `ShokoEvent:EpisodeUpdated` for EACH episode (not FileMatched):

```
22:40:10 - ShokoEvent:FileHashed (×13)
22:40:13 - ShokoEvent:SeriesUpdated
22:40:13 - ShokoEvent:EpisodeUpdated (×78+ events!)
```

**Note:** Many more EpisodeUpdated events than files - Shoko updates metadata multiple times.

---

### Still Open

- [ ] Multi-season format in Jellyseerr (`"1, 2"` vs `"1,2"`?)
- [ ] Sonarr/Radarr `originalTitle` field - not present in captured payloads
- [ ] Why Sonarr/Radarr sometimes stop monitoring hash
- [ ] Fallback checker timing

---

## Captured Payloads

- `captured-webhooks/jellyseerr-movie-auto-approved.json`
- `captured-webhooks/jellyseerr-tv-auto-approved.json`
- `captured-webhooks/radarr-grab.json`
- `captured-webhooks/sonarr-grab.json`
- `captured-webhooks/radarr-import.json`
- `captured-webhooks/sonarr-import.json` ← NEW (season pack)

**All captured!**
