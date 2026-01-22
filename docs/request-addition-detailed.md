# Request Addition: Detailed Specification

**Date:** 2026-01-21
**Purpose:** Exact step-by-step specification for all 4 media paths

---

## Table of Contents

1. [Flow Summary](#flow-summary)
2. [Phase 1: Request Creation (Jellyseerr)](#phase-1-request-creation)
3. [Phase 2: Indexer Grab (Radarr/Sonarr)](#phase-2-indexer-grab)
4. [Phase 3: Download Progress (qBittorrent)](#phase-3-download-progress)
5. [Phase 4: Import (Radarr/Sonarr)](#phase-4-import)
6. [Phase 5: Verification (DIVERGENCE POINT)](#phase-5-verification)
7. [Correlation Strategy](#correlation-strategy)
8. [is_anime Detection](#is_anime-detection)
9. [Known Bugs & Fixes](#known-bugs--fixes)

---

## Flow Summary

```
Phase 1        Phase 2         Phase 3          Phase 4         Phase 5
─────────────────────────────────────────────────────────────────────────

Jellyseerr  →  Radarr/Sonarr  →  qBittorrent  →  Radarr/Sonarr  →  Verification
   ↓              ↓                 ↓                ↓                ↓
APPROVED      INDEXED          DOWNLOADING       IMPORTING        AVAILABLE
                                                     │
                                                     ├── Path 1: Regular Movie  → Jellyfin TMDB
                                                     ├── Path 2: Regular TV     → Jellyfin TVDB
                                                     ├── Path 3: Anime Movie   → Shoko → Jellyfin
                                                     └── Path 4: Anime TV      → Shoko → Jellyfin
```

**Key Insight:** Paths 1-4 are IDENTICAL through Phase 4. They only diverge at Phase 5 (Verification).

---

## Phase 1: Request Creation

### Trigger
Jellyseerr webhook: `MEDIA_PENDING` or `MEDIA_AUTO_APPROVED`

### Webhook Payload (Jellyseerr)

**Movie Request:**
```json
{
  "notification_type": "MEDIA_AUTO_APPROVED",
  "subject": "Chainsaw Man: The Movie - Reze Arc",
  "image": "https://image.tmdb.org/t/p/w600_and_h900_bestv2/...",
  "media": {
    "media_type": "movie",
    "tmdbId": "1386807",
    "tvdbId": null,
    "status": "PENDING"
  },
  "request": {
    "request_id": "14",
    "requestedBy_username": "adept"
  },
  "extra": []
}
```

**TV Series Request (CAPTURED 2026-01-21):**
```json
{
  "notification_type": "MEDIA_AUTO_APPROVED",
  "subject": "Insomniacs After School (2023)",
  "image": "https://image.tmdb.org/t/p/w600_and_h900_bestv2/qChtK3uuCc5L5CpSeBpVV4MFRHD.jpg",
  "media": {
    "media_type": "tv",
    "tmdbId": "155440",
    "tvdbId": "414562",
    "status": "PENDING"
  },
  "request": {
    "request_id": "66",
    "requestedBy_username": "adept"
  },
  "extra": [
    {"name": "Requested Seasons", "value": "1"}
  ]
}
```

### Key Fields to Extract

| Field | Source | Required | Notes |
|-------|--------|----------|-------|
| `title` | `subject` | YES | Display name (includes year) |
| `media_type` | `media.media_type` | YES | "movie" or "tv" |
| `tmdb_id` | `media.tmdbId` | YES | Present for both movies and TV |
| `tvdb_id` | `media.tvdbId` | TV only | Present for TV shows |
| `jellyseerr_id` | `request.request_id` | YES | For Jellyseerr correlation |
| `poster_url` | `image` | YES | Direct field, NOT in extra array |
| `requested_by` | `request.requestedBy_username` | NO | For UI |
| `requested_seasons` | `extra[name="Requested Seasons"].value` | TV only | Which season(s) requested |

**Note:** `extra["Requested Seasons"]` contains WHICH season was requested (e.g., "1"), NOT the total episode count. Episode count must come from Sonarr's Grab webhook.

### Correlation Logic (Phase 1)

```python
# BEFORE creating: Check for existing ACTIVE request
existing = await correlator.find_active_by_any(
    db,
    jellyseerr_id=jellyseerr_id,  # Exact match
    tmdb_id=tmdb_id,
    tvdb_id=tvdb_id,
    exclude_states=[AVAILABLE, DELETED],
)

if existing:
    # DON'T create duplicate - maybe update?
    logger.warning(f"Request already exists: {existing.id}")
    return existing

# CREATE new request
request = MediaRequest(
    title=subject,
    media_type=media_type,
    tmdb_id=tmdb_id,
    tvdb_id=tvdb_id,
    jellyseerr_id=jellyseerr_id,
    poster_url=poster_url,
    requested_by=username,
    state=APPROVED,  # or REQUESTED if MEDIA_PENDING
    is_anime=detect_is_anime(payload),  # See is_anime Detection section
)
```

### State Transition

```
[None] → REQUESTED  (if MEDIA_PENDING)
[None] → APPROVED   (if MEDIA_AUTO_APPROVED)
```

### Data Stored After Phase 1

```python
MediaRequest(
    id=14,
    title="Chainsaw Man: The Movie - Reze Arc",
    media_type="movie",
    state="approved",
    tmdb_id=1386807,
    tvdb_id=None,
    jellyseerr_id=14,
    poster_url="https://...",
    requested_by="adept",
    is_anime=True,  # Detected from root folder or tags
    # NOT YET SET:
    qbit_hash=None,
    radarr_id=None,
    sonarr_id=None,
    quality=None,
    indexer=None,
    final_path=None,
)
```

---

## Phase 2: Indexer Grab

### Trigger
Radarr webhook: `Grab` (for movies)
Sonarr webhook: `Grab` (for TV)

### Webhook Payload (Radarr Grab)

```json
{
  "eventType": "Grab",
  "movie": {
    "id": 123,
    "title": "Chainsaw Man: The Movie - Reze Arc",
    "year": 2025,
    "tmdbId": 1386807,
    "imdbId": "tt32353804"
  },
  "remoteMovie": {
    "tmdbId": 1386807,
    "imdbId": "tt32353804",
    "title": "Chainsaw Man: The Movie - Reze Arc",
    "year": 2025
  },
  "release": {
    "quality": "Bluray-1080p",
    "qualityVersion": 1,
    "releaseTitle": "Chainsaw.Man.Reze.Arc.2025.1080p.BluRay.x264",
    "indexer": "Nyaa",
    "size": 4500000000
  },
  "downloadClient": "qBittorrent",
  "downloadId": "ABC123DEF456789..."
}
```

### Webhook Payload (Sonarr Grab)

```json
{
  "eventType": "Grab",
  "series": {
    "id": 456,
    "title": "Frieren: Beyond Journey's End",
    "tvdbId": 424536,
    "imdbId": "tt21621236"
  },
  "episodes": [
    {
      "seasonNumber": 1,
      "episodeNumber": 1,
      "title": "The Journey's End"
    }
  ],
  "release": {
    "quality": "WEBDL-1080p",
    "releaseTitle": "Frieren.S01E01.1080p.WEB-DL",
    "indexer": "Nyaa",
    "size": 1500000000
  },
  "downloadClient": "qBittorrent",
  "downloadId": "XYZ789ABC123..."
}
```

### Key Fields to Extract

| Field | Radarr Source | Sonarr Source | Required | Notes |
|-------|---------------|---------------|----------|-------|
| `download_id` | `downloadId` | `downloadId` | **CRITICAL** | qBit hash - PRIMARY correlation key |
| `arr_id` | `movie.id` | `series.id` | YES | For deletion sync |
| `tmdb_id` | `movie.tmdbId` | N/A | YES (movie) | Secondary correlation |
| `tvdb_id` | N/A | `series.tvdbId` | YES (tv) | Secondary correlation |
| `quality` | `release.quality` | `release.quality` | NO | Display |
| `indexer` | `release.indexer` | `release.indexer` | NO | Display |
| `year` | `movie.year` | N/A | NO | Display |

### Correlation Logic (Phase 2)

```python
# CRITICAL: This is where the correlation bug happens
# We MUST use download_id as primary, but it's not stored yet on the request

# Current (BROKEN):
request = await correlator.find_by_any(
    db,
    tmdb_id=tmdb_id,  # This matches OLD request if re-requesting
    qbit_hash=download_id,  # This is NEW hash, won't match anything
)

# Proposed (FIXED):
request = await correlator.find_active_request(
    db,
    tmdb_id=tmdb_id,  # For movies
    tvdb_id=tvdb_id,  # For TV
    exclude_states=[AVAILABLE, DELETED],
    order_by="created_at DESC",  # Get MOST RECENT active request
)

# IMPORTANT: download_id is NEW at this point
# We can't use it for correlation yet - we STORE it here for future phases
```

### State Transition

```
APPROVED → INDEXED
```

### Data Stored After Phase 2

```python
# UPDATE existing request
request.qbit_hash = "ABC123DEF456789..."  # CRITICAL: Store for future correlation
request.radarr_id = 123  # or sonarr_id
request.quality = "Bluray-1080p"
request.indexer = "Nyaa"
request.year = 2025
request.state = "indexed"
```

---

## Phase 3: Download Progress

### Trigger
qBittorrent polling (every 5 seconds for active downloads)

### Data Source
qBittorrent API: `GET /api/v2/torrents/info`

```json
{
  "hash": "abc123def456789...",
  "name": "Chainsaw.Man.Reze.Arc.2025.1080p.BluRay.x264",
  "progress": 0.75,
  "state": "downloading",
  "eta": 1800
}
```

### Correlation Logic (Phase 3)

```python
# Use qbit_hash - this is the ONLY reliable key at this phase
request = await correlator.find_by_hash(db, qbit_hash)

# Current (BROKEN): find_by_hash has NO state filtering
# If old completed request has same hash (re-seed?), it matches

# Proposed (FIXED):
request = await correlator.find_active_by_hash(
    db,
    qbit_hash,
    exclude_states=[AVAILABLE, DELETED],
)
```

### State Transitions

```
INDEXED → DOWNLOADING      (first progress update, progress > 0)
DOWNLOADING → DOWNLOADING  (progress updates, 0 < progress < 100)
DOWNLOADING → DOWNLOAD_DONE (progress = 100, but not imported yet)
```

### Data Stored During Phase 3

```python
request.download_progress = 75  # Updated continuously
request.state = "downloading"   # Or "download_done"
```

---

## Phase 4: Import

### Trigger
Radarr webhook: `Download` (import complete)
Sonarr webhook: `Download` (import complete)

### Webhook Payload (Radarr Import)

```json
{
  "eventType": "Download",
  "movie": {
    "id": 123,
    "title": "Chainsaw Man: The Movie - Reze Arc",
    "tmdbId": 1386807
  },
  "movieFile": {
    "id": 789,
    "relativePath": "Chainsaw Man - The Movie - Reze Arc (2025)/movie.mkv",
    "path": "/data/anime/movies/Chainsaw Man - The Movie - Reze Arc (2025)/movie.mkv",
    "quality": "Bluray-1080p"
  },
  "downloadClient": "qBittorrent",
  "downloadId": "ABC123DEF456789..."
}
```

### Webhook Payload (Sonarr Import)

```json
{
  "eventType": "Download",
  "series": {
    "id": 456,
    "title": "Frieren: Beyond Journey's End",
    "tvdbId": 424536
  },
  "episodeFile": {
    "id": 1011,
    "relativePath": "Season 01/Frieren.S01E01.1080p.WEB-DL.mkv",
    "path": "/data/anime/shows/Frieren/Season 01/Frieren.S01E01.mkv",
    "quality": "WEBDL-1080p"
  },
  "downloadClient": "qBittorrent",
  "downloadId": "XYZ789ABC123..."
}
```

### Key Fields to Extract

| Field | Radarr Source | Sonarr Source | Required | Notes |
|-------|---------------|---------------|----------|-------|
| `download_id` | `downloadId` | `downloadId` | YES | Should match stored qbit_hash |
| `final_path` | `movieFile.path` | `episodeFile.path` | **CRITICAL** | For Shoko correlation |
| `arr_id` | `movie.id` | `series.id` | NO | Already stored |

### Correlation Logic (Phase 4)

```python
# Use download_id (qbit hash) - MOST RELIABLE at this phase
request = await correlator.find_active_by_hash(
    db,
    qbit_hash=download_id,
    exclude_states=[AVAILABLE, DELETED],
)

# Fallback to tmdb_id/tvdb_id if hash not found
if not request:
    request = await correlator.find_active_by_any(
        db,
        tmdb_id=tmdb_id,
        tvdb_id=tvdb_id,
        exclude_states=[AVAILABLE, DELETED],
    )
```

### State Transition

```
DOWNLOAD_DONE → IMPORTING   (or DOWNLOADING → IMPORTING if we missed the done state)
```

### Data Stored After Phase 4

```python
request.final_path = "/data/anime/movies/Chainsaw Man.../movie.mkv"  # CRITICAL for Shoko
request.state = "importing"
```

### DIVERGENCE POINT

After Phase 4, we check `is_anime` flag to determine which verification path:

```python
if request.is_anime:
    # Wait for Shoko SignalR events (Phase 5c/5d)
    pass
else:
    # Wait for Jellyfin webhook or poll (Phase 5a/5b)
    pass
```

---

## Phase 5: Verification

### Phase 5a: Regular Movie (Path 1)

**Trigger Options:**
1. Jellyfin webhook: `ItemAdded` (ItemType=Movie)
2. Fallback checker: Poll every 30 seconds

**Jellyfin Search API:**
```
GET /Items?IncludeItemTypes=Movie&AnyProviderIdEquals=Tmdb.{tmdb_id}
```

**Correlation:** `tmdb_id` → Jellyfin provider IDs

**State Transition:**
```
IMPORTING → AVAILABLE
```

---

### Phase 5b: Regular TV (Path 2)

**Trigger Options:**
1. Jellyfin webhook: `ItemAdded` (ItemType=Episode)
2. Fallback checker: Poll every 30 seconds ← **NEEDS IMPLEMENTATION**

**Jellyfin Search API:**
```
GET /Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tvdb.{tvdb_id}
```

**Correlation:** `tvdb_id` → Jellyfin provider IDs

**Current Bug:** Fallback checker has `media_type == "movie"` filter, so TV never gets checked.

**State Transition:**
```
IMPORTING → AVAILABLE
```

---

### Phase 5c: Anime Movie (Path 3)

**Trigger:** Shoko SignalR `FileMatched` event

**Shoko SignalR Event:**
```json
{
  "EventType": "FileMatched",
  "FileInfo": {
    "FileID": 12345,
    "RelativePath": "anime/movies/Chainsaw Man.../movie.mkv",
    "CrossReferences": [...]  // AniDB mappings
  }
}
```

**Correlation:**
1. PRIMARY: `final_path` == `/data/{RelativePath}`
2. FALLBACK: Filename pattern match

**Flow:**
```
IMPORTING → FileMatched(cross_refs=true)  → AVAILABLE
IMPORTING → FileMatched(cross_refs=false) → ANIME_MATCHING → Fallback checker → AVAILABLE
```

**Fallback Verification (if stuck at ANIME_MATCHING):**
```
1. Jellyfin: /Items?IncludeItemTypes=Movie&AnyProviderIdEquals=Tmdb.{tmdb_id}
2. Jellyfin: /Items?AnyProviderIdEquals=Tmdb.{tmdb_id}  (any type)
3. Jellyfin: /Items?SearchTerm={title}&Years={year}    (title search)
```

---

### Phase 5d: Anime TV (Path 4)

**Trigger:** Shoko SignalR `FileMatched` event

**Correlation:** Same as Phase 5c (final_path)

**Flow:**
```
IMPORTING → FileMatched(cross_refs=true)  → AVAILABLE
IMPORTING → FileMatched(cross_refs=false) → ANIME_MATCHING → Fallback checker → AVAILABLE
```

**Fallback Verification (if stuck at ANIME_MATCHING):**
```
1. Jellyfin: /Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tvdb.{tvdb_id}
2. Jellyfin: /Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tmdb.{tmdb_id}
3. Jellyfin: /Items?SearchTerm={title}  (title search)
```

**Current Bug:** No TVDB lookup implemented for anime TV fallback.

---

## Correlation Strategy

### Priority Order

```
1. download_id (qbit hash)  → UNIQUE per download, most reliable
2. jellyseerr_id           → Unique per request, but not available in *arr webhooks
3. tmdb_id + state filter  → Good for movies, may have duplicates
4. tvdb_id + state filter  → Good for TV, may have duplicates
5. final_path              → Good for Shoko correlation
6. title + year            → Last resort fuzzy match
```

### State Filtering

**CRITICAL:** All correlation queries MUST exclude terminal states.

```python
ACTIVE_STATES = [REQUESTED, APPROVED, INDEXED, DOWNLOADING, DOWNLOAD_DONE, IMPORTING, ANIME_MATCHING]
TERMINAL_STATES = [AVAILABLE, DELETED, FAILED]

# Every find_by_X method should:
# 1. Filter to ACTIVE_STATES (or exclude TERMINAL_STATES)
# 2. Order by created_at DESC (most recent first)
# 3. Return single best match, not first found
```

### Current vs Proposed Correlator

```python
# CURRENT (BROKEN)
class EventCorrelator:
    async def find_by_hash(self, db, qbit_hash):
        # BUG: No state filtering at all!
        stmt = select(MediaRequest).where(
            MediaRequest.qbit_hash.ilike(qbit_hash),
        )
        return result.scalar_one_or_none()

# PROPOSED (FIXED)
class EventCorrelator:
    async def find_by_hash(self, db, qbit_hash, exclude_states=None):
        exclude = exclude_states or [RequestState.AVAILABLE, RequestState.DELETED]
        stmt = select(MediaRequest).where(
            MediaRequest.qbit_hash.ilike(qbit_hash),
            MediaRequest.state.notin_(exclude),
        ).order_by(MediaRequest.created_at.desc())
        return result.scalar_one_or_none()
```

---

## is_anime Detection

### Why It Matters

We need to know `is_anime` at Phase 4 (Import) to decide whether to:
- Wait for Shoko events (anime)
- Wait for Jellyfin events (regular)

### Detection Methods (Priority Order)

1. **Root Folder Path** (most reliable)
   ```python
   if final_path.startswith("/data/anime/"):
       is_anime = True
   ```

2. **Radarr/Sonarr Tags** (if configured)
   ```json
   // Radarr Grab payload
   "movie": {
     "tags": ["anime"]  // If user tags anime in Radarr
   }
   ```

3. **Jellyseerr Keywords** (less reliable)
   ```json
   // Check genre or keywords from TMDB
   "extra": [
     {"name": "Genres", "value": "Animation"}  // Not always anime
   ]
   ```

4. **Manual Override**
   - API endpoint: `PATCH /requests/{id}` with `is_anime=true`
   - Dashboard button: "Mark as Anime"

### Recommended Implementation

```python
def detect_is_anime(payload: dict, final_path: str = None) -> bool:
    # Method 1: Root folder (most reliable, but only available at Import)
    if final_path:
        if "/anime/" in final_path:
            return True
        if "/movies/" in final_path and "/anime" not in final_path:
            return False
        if "/tv/" in final_path and "/anime" not in final_path:
            return False

    # Method 2: Check tags from *arr
    movie = payload.get("movie", {})
    series = payload.get("series", {})
    tags = movie.get("tags", []) or series.get("tags", [])
    if "anime" in [t.lower() for t in tags]:
        return True

    # Method 3: Default based on root folder config
    # Could check against settings.ANIME_ROOT_FOLDERS

    return False  # Default to non-anime
```

---

## Known Bugs & Fixes

### Bug 1: Correlation Matches Wrong Request

**Symptom:** Radarr Grab webhook updates OLD completed request instead of NEW one.

**Root Cause:** `find_by_hash()` has no state filtering; `find_by_tmdb()` may match first record.

**Fix:**
```python
# In correlator.py
async def find_by_hash(self, db, qbit_hash, exclude_states=None):
    exclude = exclude_states or [RequestState.AVAILABLE, RequestState.DELETED]
    stmt = select(MediaRequest).where(
        MediaRequest.qbit_hash.ilike(qbit_hash),
        MediaRequest.state.notin_(exclude),
    ).order_by(MediaRequest.created_at.desc())
    return result.scalar_one_or_none()
```

### Bug 2: TV Fallback Missing

**Symptom:** Regular TV shows stuck at IMPORTING forever if Jellyfin webhook fails.

**Root Cause:** `jellyfin_verifier.py` line 170-174 has `media_type == "movie"` filter.

**Fix:**
```python
# Remove movie filter, add TVDB lookup
stmt = select(MediaRequest).where(
    MediaRequest.state.in_([RequestState.ANIME_MATCHING, RequestState.IMPORTING]),
    # MediaRequest.media_type == "movie",  # REMOVE THIS
    or_(
        MediaRequest.tmdb_id.isnot(None),
        MediaRequest.tvdb_id.isnot(None),
    ),
)

# Add Jellyfin TVDB lookup
async def find_item_by_tvdb(self, tvdb_id: int):
    return await self.jellyfin.get(
        f"/Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tvdb.{tvdb_id}"
    )
```

### Bug 3: Anime ID Mismatch (Shoko/Shokofin)

**Symptom:** Anime movies like Violet Evergarden compilation stuck at ANIME_MATCHING.

**Root Cause:**
- Jellyseerr requests as Movie (TMDB 1052946)
- Shoko categorizes as TV Special (AniDB 12138)
- Shokofin presents as TV episodes
- Fallback checker searches for Movie, finds nothing

**Fix:** Dual search fallback
```python
async def verify_anime_in_jellyfin(request):
    # Try 1: Movie by TMDB
    if item := await jellyfin.find_by_tmdb(request.tmdb_id, "Movie"):
        return item

    # Try 2: Series by TMDB (Shoko may have categorized as TV)
    if item := await jellyfin.find_by_tmdb(request.tmdb_id, "Series"):
        return item

    # Try 3: Any type by TMDB
    if item := await jellyfin.find_by_tmdb(request.tmdb_id):
        return item

    # Try 4: Title search
    if item := await jellyfin.search_by_title(request.title, request.year):
        return item

    return None
```

### Bug 4: Poster URL Missing

**Symptom:** Dashboard shows placeholder image instead of poster.

**Root Cause:** Jellyseerr `extra` array may have different poster field names.

**Fix:**
```python
def extract_poster_url(payload):
    extra = payload.get("extra", [])

    # Try different field names
    for item in extra:
        name = item.get("name", "")
        if "poster" in name.lower():
            return item.get("value")

    # Fallback: Construct from TMDB ID
    tmdb_id = payload.get("media", {}).get("tmdbId")
    if tmdb_id:
        return f"https://image.tmdb.org/t/p/w500/{tmdb_id}"  # Needs API call

    return None
```

### Bug 5: Library Sync Phantom Requests

**Symptom:** Requests appear that user didn't make.

**Root Cause:** Library sync creates new requests for existing Jellyfin items without checking source.

**Fix:** Mark sync-created requests with `source="library_sync"` and different UI treatment.

---

## Implementation Priority

| Priority | Fix | Impact | Effort |
|----------|-----|--------|--------|
| 1 | Correlation state filtering | Fixes wrong request matching | Low |
| 2 | TV fallback (remove movie filter) | Fixes regular TV stuck | Low |
| 3 | Add TVDB lookup | Enables TV fallback | Low |
| 4 | Anime dual search fallback | Fixes compilation movies | Medium |
| 5 | is_anime detection | Enables path divergence | Medium |
| 6 | Poster URL extraction | Cosmetic | Low |

---

## Next Steps

1. [ ] Review this specification with user
2. [ ] Implement correlation fix (Priority 1)
3. [ ] Test with all 4 paths
4. [ ] Implement remaining fixes in priority order
