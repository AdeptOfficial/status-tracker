# Phase 4: Import

**Source:** Radarr (movies) or Sonarr (TV)
**Trigger:** Webhook `eventType: "Download"` (confusingly named - means import complete)
**State Transitions:**
- Movies: `DOWNLOADED` → `IMPORTING`
- TV Episodes: `DOWNLOADED` → `IMPORTING` (per-episode)

---

## Overview

After qBittorrent completes the download, Radarr/Sonarr:
1. Detects the completed download
2. Moves/copies/hardlinks file to final library location
3. Renames according to naming scheme
4. Fires "Download" webhook (means import complete, not download complete)

This phase provides the **final_path** - critical for:
- Shoko correlation (anime)
- Jellyfin verification (non-anime)
- is_anime detection (path-based)

---

## Webhook Payloads

### Radarr Import (Movie)

```json
{
  "eventType": "Download",
  "movie": {
    "id": 52,
    "title": "Violet Evergarden: The Movie",
    "year": 2020,
    "tmdbId": 533514,
    "imdbId": "tt8652818",
    "folderPath": "/data/anime/movies/Violet Evergarden - The Movie (2020)"
  },
  "movieFile": {
    "id": 789,
    "relativePath": "Violet Evergarden - The Movie (2020).mkv",
    "path": "/data/anime/movies/Violet Evergarden - The Movie (2020)/movie.mkv",
    "quality": "Bluray-1080p",
    "size": 1181116032
  },
  "downloadClient": "qBittorrent (VPN)",
  "downloadId": "C2C60F66C126652A86F7F2EE73DC83D4E255929E",
  "eventType": "Download",
  "instanceName": "Radarr"
}
```

### Sonarr Import (TV - Season Pack)

**UPDATED from captured webhook (2026-01-21):** For season packs, Sonarr sends **ONE webhook with ALL episode files**!

```json
{
  "eventType": "Download",
  "series": {
    "id": 23,
    "title": "Lycoris Recoil",
    "tvdbId": 414057,
    "type": "anime",
    "path": "/data/anime/shows/Lycoris Recoil"
  },
  "episodes": [
    {"id": 739, "episodeNumber": 1, "seasonNumber": 1, "title": "Easy does it"},
    {"id": 740, "episodeNumber": 2, "seasonNumber": 1, "title": "The more the merrier"},
    "... (all 13 episodes)"
  ],
  "episodeFiles": [
    {"relativePath": "Season 1/Lycoris.Recoil.S01E01.mkv", "path": "/data/anime/shows/.../S01E01.mkv"},
    {"relativePath": "Season 1/Lycoris.Recoil.S01E02.mkv", "path": "/data/anime/shows/.../S01E02.mkv"},
    "... (all 13 files)"
  ],
  "sourcePath": "/data/downloads/complete/Lycoris.Recoil.S01...",
  "destinationPath": "/data/anime/shows/Lycoris Recoil/Season 1",
  "downloadClient": "qBittorrent (VPN)",
  "downloadId": "3F92992E2FBEB6EBB251304236BF5E0B600A91C3",
  "instanceName": "Sonarr"
}
```

**Key differences from single episode:**
- `episodeFiles` (plural) array instead of `episodeFile` (singular)
- `episodes` array contains ALL episodes being imported
- `destinationPath` is the season folder, not individual file

**Import types:**
| Type | Webhook Count | Field |
|------|--------------|-------|
| Season pack | 1 webhook | `episodeFiles[]` (plural) |
| Individual episodes | 1 per episode | `episodeFile` (singular) |

---

## Correlation

### Primary: downloadId (qBit hash)

```python
# Movies
request = await db.query(MediaRequest).filter(
    MediaRequest.qbit_hash == download_id,
    MediaRequest.state.not_in([RequestState.AVAILABLE, RequestState.DELETED])
).first()

# TV - find request, then episode
request = await db.query(MediaRequest).join(Episode).filter(
    Episode.qbit_hash == download_id,
    MediaRequest.state.not_in([RequestState.AVAILABLE, RequestState.DELETED])
).first()
```

### Fallback: tmdb_id / tvdb_id

If hash missing (manual import):

```python
# Movie fallback
request = await db.query(MediaRequest).filter(
    MediaRequest.tmdb_id == tmdb_id,
    MediaRequest.media_type == "movie",
    MediaRequest.state.not_in([RequestState.AVAILABLE, RequestState.DELETED])
).first()

# TV fallback
request = await db.query(MediaRequest).filter(
    MediaRequest.tvdb_id == tvdb_id,
    MediaRequest.media_type == "tv",
    MediaRequest.state.not_in([RequestState.AVAILABLE, RequestState.DELETED])
).first()
```

---

## Flow

### Movies (Simple)

```
Radarr Import webhook
    │
    ▼
┌─────────────────────────────────┐
│ Find request by downloadId      │
│ (fallback: tmdb_id)             │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Store final_path on request     │
│ Detect is_anime from path       │
│ Transition: DOWNLOADED→IMPORTING│
└─────────────────────────────────┘
    │
    ▼
    Done (wait for Phase 5)
```

### TV Shows (Per-Episode)

```
Sonarr Import webhook (per episode)
    │
    ▼
┌─────────────────────────────────┐
│ Find request by downloadId      │
│ (fallback: tvdb_id)             │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Find Episode row by             │
│ season_number + episode_number  │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Update Episode:                 │
│ - final_path                    │
│ - state = IMPORTING             │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Recalculate request state       │
│ from all episode states         │
└─────────────────────────────────┘
    │
    ▼
    Done (wait for Phase 5)
```

---

## Data Updates

### Movies

```python
async def handle_radarr_import(payload: dict, db: AsyncSession):
    download_id = payload.get("downloadId")
    movie_file = payload.get("movieFile", {})

    request = await find_request_by_hash_or_tmdb(db, download_id, payload["movie"]["tmdbId"])
    if not request:
        return None

    # Store final path
    request.final_path = movie_file.get("path")

    # Detect anime from path
    request.is_anime = "/anime/" in request.final_path.lower()

    # Transition state
    request.state = RequestState.IMPORTING

    return request
```

### TV Episodes

```python
async def handle_sonarr_import(payload: dict, db: AsyncSession):
    download_id = payload.get("downloadId")
    episode_file = payload.get("episodeFile", {})
    episodes_data = payload.get("episodes", [])

    request = await find_request_by_hash_or_tvdb(db, download_id, payload["series"]["tvdbId"])
    if not request:
        return None

    # Update each episode in the webhook
    for ep_data in episodes_data:
        episode = await db.query(Episode).filter(
            Episode.request_id == request.id,
            Episode.season_number == ep_data["seasonNumber"],
            Episode.episode_number == ep_data["episodeNumber"]
        ).first()

        if episode:
            episode.final_path = episode_file.get("path")
            episode.state = EpisodeState.IMPORTING

    # Detect anime from path (first time only)
    if request.is_anime is None:
        request.is_anime = "/anime/" in episode_file.get("path", "").lower()

    # Recalculate aggregate state
    request.state = await calculate_aggregate_state(db, request.id)

    return request
```

---

## is_anime Detection

At Phase 4, we have `final_path` - the **most reliable** way to detect anime:

```python
def detect_is_anime(final_path: str) -> bool:
    """Detect if content is anime based on library path."""
    if not final_path:
        return False

    path_lower = final_path.lower()
    return "/anime/" in path_lower
```

| Path | is_anime |
|------|----------|
| `/data/anime/movies/...` | `True` |
| `/data/anime/shows/...` | `True` |
| `/data/movies/...` | `False` |
| `/data/tv/...` | `False` |

**Why path-based?** Tags can be wrong, genres are unreliable. Path reflects how Radarr/Sonarr is configured.

---

## Display During Import

### Movies

```
Violet Evergarden: The Movie (2020)
Importing...
```

### TV Shows

```
Lycoris Recoil (2022)
Season 1 • Importing • 5/13 imported
```

Count logic:
```python
imported_count = await db.query(Episode).filter(
    Episode.request_id == request.id,
    Episode.state.in_([EpisodeState.IMPORTING, EpisodeState.AVAILABLE])
).count()
```

---

## Edge Cases

### Multiple Import Webhooks (Same Episode)

Can happen with quality upgrades:

```python
if episode.state == EpisodeState.AVAILABLE:
    # Already imported - this is an upgrade
    logger.info(f"Quality upgrade for {request.title} S{ep.season}E{ep.episode}")
    episode.final_path = new_path  # Update path
    # Don't change state - still AVAILABLE
    return request
```

### Missing Episode Row

Episode not created in Phase 2 (edge case):

```python
if not episode:
    logger.warning(f"Import for unknown episode: {request.title} S{s}E{e}")
    # Create episode row on-the-fly
    episode = Episode(
        request_id=request.id,
        season_number=ep_data["seasonNumber"],
        episode_number=ep_data["episodeNumber"],
        episode_title=ep_data.get("title"),
        state=EpisodeState.IMPORTING,
        final_path=episode_file.get("path")
    )
    db.add(episode)
```

### Import Without Download (Manual Add)

No downloadId present:

```python
if not download_id:
    # Manual import - correlate by media ID only
    request = await find_active_by_tvdb(db, tvdb_id)
```

---

## DIVERGENCE POINT

After Phase 4, check `is_anime` to determine verification path:

```python
if request.is_anime:
    # → Phase 5: Anime path (Shoko → Jellyfin)
    # Next states: IMPORTING → ANIME_MATCHING → AVAILABLE
    pass
else:
    # → Phase 5: Non-anime path (direct Jellyfin)
    # Next states: IMPORTING → AVAILABLE
    pass
```

---

## Previous Phase

← [Phase 3: Download Progress](phase-3-download-progress.md)

## Next Phase

→ [Phase 5: Verification](phase-5-verification.md)
