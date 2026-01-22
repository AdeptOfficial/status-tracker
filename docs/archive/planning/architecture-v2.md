# Status-Tracker Architecture v2

**Date:** 2026-01-21
**Purpose:** High-level architecture for all media flows, sync, deletion, and edge cases

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [Request Addition (4 Paths)](#request-addition-4-paths)
3. [Library Sync](#library-sync)
4. [Deletion Flow](#deletion-flow)
5. [Edge Cases](#edge-cases)
6. [Data Model](#data-model)

---

## Core Concepts

### Media Types

| Type | Download Manager | ID System | Jellyfin Type |
|------|------------------|-----------|---------------|
| Regular Movie | Radarr | TMDB | Movie |
| Regular TV | Sonarr | TVDB | Series |
| Anime Movie | Radarr | TMDB → AniDB | Movie (via Shokofin) |
| Anime TV | Sonarr | TVDB → AniDB | Series (via Shokofin) |

### Request States

```
REQUESTED      → User submitted request (not yet approved)
APPROVED       → Jellyseerr approved, sent to *arr
INDEXED        → *arr found release on indexer
DOWNLOADING    → qBittorrent actively downloading
DOWNLOAD_DONE  → Download complete, awaiting import
IMPORTING      → *arr imported to library folder
ANIME_MATCHING → Shoko processing (anime only)
AVAILABLE      → Verified in Jellyfin, ready to watch
DELETED        → Removed from all services
```

### Correlation Keys

```
PRIMARY (unique per download):
  - download_id (qBittorrent hash)

SECONDARY (may have duplicates):
  - tmdb_id (movies, some TV)
  - tvdb_id (TV shows)
  - jellyseerr_request_id

TERTIARY (fallback):
  - title + year
  - file_path
```

---

## Request Addition (4 Paths)

### Overview Diagram

```
┌──────────────────────────────────────────────────────────────────────────┐
│                              USER REQUEST                                 │
│                           (via Jellyseerr)                               │
└──────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │      Jellyseerr Webhook       │
                    │   MEDIA_PENDING / APPROVED    │
                    └───────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
                    ▼                               ▼
            ┌───────────────┐               ┌───────────────┐
            │     MOVIE     │               │    TV SHOW    │
            │   (Radarr)    │               │   (Sonarr)    │
            └───────────────┘               └───────────────┘
                    │                               │
        ┌───────────┴───────────┐       ┌───────────┴───────────┐
        │                       │       │                       │
        ▼                       ▼       ▼                       ▼
┌───────────────┐       ┌───────────────┐       ┌───────────────┐       ┌───────────────┐
│    REGULAR    │       │     ANIME     │       │    REGULAR    │       │     ANIME     │
│     MOVIE     │       │     MOVIE     │       │      TV       │       │      TV       │
│   (Path 1)    │       │   (Path 3)    │       │   (Path 2)    │       │   (Path 4)    │
└───────────────┘       └───────────────┘       └───────────────┘       └───────────────┘
        │                       │                       │                       │
        └───────────────────────┴───────────────────────┴───────────────────────┘
                                            │
                                            ▼
                              ┌─────────────────────────┐
                              │    COMMON DOWNLOAD      │
                              │        FLOW             │
                              └─────────────────────────┘
```

### Phase 1: Request Creation (COMMON)

```
Trigger: Jellyseerr webhook (MEDIA_PENDING or MEDIA_AUTO_APPROVED)

Action:
  1. Extract: title, year, tmdb_id, media_type, user_id
  2. Check for existing active request (same tmdb_id, not AVAILABLE/DELETED)
     - If exists: Log warning, skip creation (or update?)
     - If not: Create new request
  3. Fetch poster_url from TMDB API
  4. Set state: REQUESTED or APPROVED (based on webhook type)
  5. Store jellyseerr_request_id for correlation

Data Stored:
  - title, year, media_type (movie/tv)
  - tmdb_id, jellyseerr_request_id
  - poster_url
  - is_anime (from Jellyseerr tags or root folder)
  - user_id, username
  - state: APPROVED
```

### Phase 2: Indexer Grab (COMMON)

```
Trigger: Radarr/Sonarr "Grab" webhook

Correlation:
  1. Try download_id (qbit hash) → most reliable
  2. Try tmdb_id (Radarr) or tvdb_id (Sonarr)
  3. Filter: Only match requests in APPROVED state
  4. If multiple matches: Use most recent

Action:
  1. Store download_id (qbit hash) → PRIMARY KEY for future correlation
  2. Store quality, indexer info
  3. Store radarr_id or sonarr_id
  4. Set state: INDEXED

Data Stored:
  - download_id (qbit hash)
  - quality, indexer
  - radarr_id / sonarr_id
```

### Phase 3: Download Progress (COMMON)

```
Trigger: qBittorrent polling (every 5s for active downloads)

Correlation:
  - download_id (qbit hash) → exact match

Action:
  1. Update progress percentage
  2. INDEXED → DOWNLOADING (on first progress)
  3. DOWNLOADING → DOWNLOAD_DONE (when progress = 100%)

Data Stored:
  - download_progress (0-100)
```

### Phase 4: Import (COMMON)

```
Trigger: Radarr/Sonarr "Download" (Import) webhook

Correlation:
  1. download_id (qbit hash) → primary
  2. tmdb_id / tvdb_id → secondary

Action:
  1. Store final_path (file location)
  2. Set state: IMPORTING
  3. DIVERGE based on is_anime flag

Data Stored:
  - final_path
```

### Phase 5a: Regular Movie Verification (Path 1)

```
Trigger:
  - Jellyfin ItemAdded webhook (ItemType=Movie)
  - OR Fallback checker (every 30s)

Correlation:
  - tmdb_id → Jellyfin provider ID lookup

Jellyfin Search:
  GET /Items?IncludeItemTypes=Movie&AnyProviderIdEquals=Tmdb.{tmdb_id}

Action:
  1. If found in Jellyfin:
     - Store jellyfin_id
     - Set state: AVAILABLE
  2. If not found:
     - Keep polling (fallback checker)

Data Stored:
  - jellyfin_id
```

### Phase 5b: Regular TV Verification (Path 2)

```
Trigger:
  - Jellyfin ItemAdded webhook (ItemType=Episode)
  - OR Fallback checker (every 30s) ← NEEDS IMPLEMENTATION

Correlation:
  - tvdb_id → Jellyfin provider ID lookup

Jellyfin Search:
  GET /Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tvdb.{tvdb_id}

Action:
  1. If found in Jellyfin:
     - Store jellyfin_id
     - Set state: AVAILABLE
  2. If not found:
     - Keep polling

Data Stored:
  - jellyfin_id
```

### Phase 5c: Anime Movie Verification (Path 3)

```
Trigger:
  - Shoko FileMatched SignalR event
  - OR Fallback checker (every 30s)

Flow:
  IMPORTING
      │
      ├─► Shoko FileMatched (cross_refs: True)
      │       │
      │       └─► AVAILABLE (if Shoko confident)
      │
      └─► Shoko FileMatched (cross_refs: False)
              │
              └─► ANIME_MATCHING
                      │
                      └─► Fallback checker polls Jellyfin

Fallback Verification:
  1. Try TMDB ID (movie): /Items?IncludeItemTypes=Movie&AnyProviderIdEquals=Tmdb.{tmdb_id}
  2. Try TMDB ID (any type): /Items?AnyProviderIdEquals=Tmdb.{tmdb_id}
  3. Try title search: /Items?SearchTerm={title}&Years={year}
  4. Try file path match (if Jellyfin indexes physical path)

Data Stored:
  - jellyfin_id
  - shoko_file_id (optional)
```

### Phase 5d: Anime TV Verification (Path 4)

```
Trigger:
  - Shoko FileMatched SignalR event
  - OR Fallback checker (every 30s) ← NEEDS IMPLEMENTATION

Flow:
  IMPORTING
      │
      ├─► Shoko FileMatched (cross_refs: True)
      │       │
      │       └─► AVAILABLE (if Shoko confident)
      │
      └─► Shoko FileMatched (cross_refs: False)
              │
              └─► ANIME_MATCHING
                      │
                      └─► Fallback checker polls Jellyfin

Fallback Verification:
  1. Try TVDB ID: /Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tvdb.{tvdb_id}
  2. Try TMDB ID (show): /Items?IncludeItemTypes=Series&AnyProviderIdEquals=Tmdb.{tmdb_id}
  3. Try title search
  4. Try AniDB ID (if Shokofin exposes it)

Data Stored:
  - jellyfin_id
  - shoko_series_id (optional)
```

---

## Library Sync

### Purpose

Sync existing Jellyfin library items to status-tracker so users can see what's already available without having to request it.

### Trigger

- Manual: "Sync Library" button in UI
- Automatic: On startup (optional)
- Scheduled: Daily sync (optional)

### Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                      LIBRARY SYNC FLOW                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │   Fetch all Jellyfin items    │
              │   (Movies, Series)            │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │   For each Jellyfin item:     │
              │   - Extract provider IDs      │
              │   - Extract metadata          │
              └───────────────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │   Check existing requests:    │
              │   - Match by jellyfin_id      │
              │   - Match by tmdb_id/tvdb_id  │
              └───────────────────────────────┘
                              │
              ┌───────────────┴───────────────┐
              │                               │
              ▼                               ▼
      ┌───────────────┐               ┌───────────────┐
      │ Request EXISTS│               │ Request DOES  │
      │               │               │ NOT EXIST     │
      └───────────────┘               └───────────────┘
              │                               │
              ▼                               ▼
      ┌───────────────┐               ┌───────────────┐
      │ Update:       │               │ Create:       │
      │ - jellyfin_id │               │ - New request │
      │ - state=AVAIL │               │ - state=AVAIL │
      │ - poster_url  │               │ - source=sync │
      └───────────────┘               └───────────────┘
```

### Sync Rules

```
1. DO NOT overwrite user-requested items that are still in progress
   - Only update if state is already AVAILABLE or if request doesn't exist

2. Mark sync-created requests differently:
   - source = "library_sync" (vs "jellyseerr")
   - requested_by = null or "system"

3. Handle duplicates:
   - If Jellyfin has item AND user requested it → Update existing request
   - If Jellyfin has item AND no request → Create with source=sync
   - If user requested AND not in Jellyfin → Keep request, don't mark available

4. Fetch metadata:
   - poster_url from Jellyfin (ImageTags)
   - title, year from Jellyfin
   - provider IDs (TMDB, TVDB, IMDB)
```

### API Endpoint

```
POST /api/library/sync
  - Triggers full library sync
  - Returns: { synced: 150, created: 10, updated: 140, errors: [] }

POST /api/library/sync/{jellyfin_id}
  - Sync single item
  - Used for real-time updates
```

---

## Deletion Flow

### Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                       DELETION SOURCES                          │
└─────────────────────────────────────────────────────────────────┘
                              │
        ┌─────────────────────┼─────────────────────┐
        │                     │                     │
        ▼                     ▼                     ▼
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│  Dashboard    │     │   Radarr/     │     │   Jellyfin    │
│  (User)       │     │   Sonarr      │     │   (External)  │
└───────────────┘     └───────────────┘     └───────────────┘
        │                     │                     │
        └─────────────────────┴─────────────────────┘
                              │
                              ▼
              ┌───────────────────────────────┐
              │     DELETION ORCHESTRATOR     │
              └───────────────────────────────┘
```

### Deletion from Dashboard (User-Initiated)

```
Trigger: User clicks "Delete" on request

Options:
  - delete_files: true/false (remove physical files)
  - delete_from_services: true/false (sync to other services)

Flow:
  1. Mark request state = DELETING
  2. If delete_from_services:
     a. Delete from Jellyseerr (by jellyseerr_request_id)
     b. Delete from Radarr/Sonarr (by radarr_id/sonarr_id)
        - If delete_files: include deleteFiles=true
     c. Delete from Shoko (for anime, by file path)
     d. Jellyfin will auto-remove on next scan
  3. Mark request state = DELETED
  4. Log deletion in deletion_log table

Sync Status per Service:
  - pending: Waiting to sync
  - acknowledged: Request sent
  - confirmed: Service confirmed deletion
  - failed: Service returned error
  - not_applicable: Service not used for this media type
```

### Deletion from Radarr/Sonarr (External)

```
Trigger: Radarr/Sonarr MovieDelete/SeriesDelete webhook

Flow:
  1. Find request by radarr_id/sonarr_id
  2. If ENABLE_DELETION_SYNC:
     a. Mark request state = DELETING
     b. Delete from OTHER services (skip the one that triggered)
     c. Mark request state = DELETED
  3. If NOT ENABLE_DELETION_SYNC:
     a. Just log the deletion
     b. Optionally mark request as DELETED
```

### Deletion Sync Matrix

| Source | Delete from Jellyseerr | Delete from Radarr | Delete from Sonarr | Delete from Shoko | Delete from Jellyfin |
|--------|------------------------|--------------------|--------------------|-------------------|----------------------|
| Dashboard | ✅ | ✅ (if movie) | ✅ (if TV) | ✅ (if anime) | ✅ (via scan) |
| Radarr | ✅ | SKIP | - | ✅ (if anime) | ✅ (via scan) |
| Sonarr | ✅ | - | SKIP | ✅ (if anime) | ✅ (via scan) |
| Jellyfin | ❓ | ❓ | ❓ | ❓ | SKIP |

### Deletion by Media Type

#### Path 1: Regular Movie Deletion

```
Services to sync:
  1. Jellyseerr (by request_id)
  2. Radarr (by radarr_id, deleteFiles=true/false)
  3. Jellyfin (automatic on library scan)

NOT applicable:
  - Sonarr (not a TV show)
  - Shoko (not anime)
```

#### Path 2: Regular TV Deletion

```
Services to sync:
  1. Jellyseerr (by request_id)
  2. Sonarr (by sonarr_id, deleteFiles=true/false)
  3. Jellyfin (automatic on library scan)

NOT applicable:
  - Radarr (not a movie)
  - Shoko (not anime)
```

#### Path 3: Anime Movie Deletion

```
Services to sync:
  1. Jellyseerr (by request_id)
  2. Radarr (by radarr_id, deleteFiles=true/false)
  3. Shoko (by file path - Shoko detects missing files)
  4. Jellyfin (automatic via Shokofin)

NOT applicable:
  - Sonarr (not a TV show)
```

#### Path 4: Anime TV Deletion

```
Services to sync:
  1. Jellyseerr (by request_id)
  2. Sonarr (by sonarr_id, deleteFiles=true/false)
  3. Shoko (by file path)
  4. Jellyfin (automatic via Shokofin)

NOT applicable:
  - Radarr (not a movie)
```

---

## Edge Cases

### Edge Case 1: Compilation Movie (Violet Evergarden)

**Problem:**
- Jellyseerr/Radarr: Movie (TMDB 1052946)
- Shoko/AniDB: TV Special (part of series AniDB 12138)
- Shokofin: Presents as TV episodes, not movie

**Solution Options:**

```
Option A: Trust Radarr (file-based)
  - If file is in /anime/movies/ → treat as movie
  - Search Jellyfin by file path instead of TMDB ID
  - Accept any Jellyfin item containing the file

Option B: Trust Shoko (metadata-based)
  - Accept that it's a TV special
  - Update request to media_type=tv
  - Search as Series instead of Movie

Option C: Dual search
  - Try Movie search first
  - If not found, try Series search
  - Accept either match

Option D: Manual override
  - Add "Mark as Available" button
  - User confirms it's in Jellyfin
  - Store jellyfin_id manually
```

**Recommended:** Option C (Dual search) with fallback to Option D

### Edge Case 2: Duplicate Requests (Same TMDB ID)

**Problem:**
- User requests Movie A
- Movie A completes, becomes AVAILABLE
- User deletes from Jellyfin (external)
- User requests Movie A again
- Webhooks correlate to OLD request (already AVAILABLE)

**Solution:**

```
Correlation Priority:
  1. Match by download_id (qbit hash) → unique per download
  2. If no download_id, match by tmdb_id WHERE state NOT IN (AVAILABLE, DELETED)
  3. If multiple active requests, use most recently created
  4. Never correlate to AVAILABLE/DELETED requests unless explicitly needed

Request Lifecycle:
  - AVAILABLE requests are "closed" - don't receive webhook updates
  - New request for same content creates NEW record
  - Old AVAILABLE record remains for history
```

### Edge Case 3: Re-download After Deletion

**Problem:**
- Request completed, AVAILABLE
- User deletes via dashboard
- User requests same content again
- Should be treated as new request, not update to deleted one

**Solution:**

```
On new Jellyseerr webhook:
  1. Check for DELETED request with same tmdb_id
  2. Do NOT reuse - create new request
  3. Deleted requests are immutable history

Correlation:
  - Exclude DELETED state from all correlation queries
```

### Edge Case 4: Partial Season Download (TV)

**Problem:**
- User requests TV series
- Only Season 1 downloads initially
- When does it become AVAILABLE?
- What about Season 2 later?

**Solution:**

```
Option A: First episode = AVAILABLE
  - Mark AVAILABLE when ANY episode hits Jellyfin
  - Simple, user can start watching

Option B: Per-season tracking
  - Track which seasons are requested vs available
  - More complex data model
  - Better accuracy

Recommended: Option A for MVP, Option B for future
```

### Edge Case 5: Download Fails / Stalls

**Problem:**
- Download starts but never completes
- qBittorrent stalls or errors
- Request stuck in DOWNLOADING forever

**Solution:**

```
Timeout mechanism:
  - If DOWNLOADING for > 7 days, mark as STALLED
  - If IMPORTING for > 1 day, mark as STALLED
  - Dashboard shows stalled requests with "Retry" option

Retry action:
  - Trigger *arr to search again
  - Or allow manual "Mark as Available" if file exists
```

---

## Data Model

### Request Table

```sql
CREATE TABLE media_request (
  id SERIAL PRIMARY KEY,

  -- Core identifiers
  title VARCHAR(255) NOT NULL,
  year INTEGER,
  media_type VARCHAR(10) NOT NULL,  -- 'movie' or 'tv'
  is_anime BOOLEAN DEFAULT FALSE,

  -- External IDs
  tmdb_id INTEGER,
  tvdb_id INTEGER,
  imdb_id VARCHAR(20),
  jellyseerr_request_id INTEGER,
  radarr_id INTEGER,
  sonarr_id INTEGER,
  jellyfin_id VARCHAR(100),

  -- Download tracking
  download_id VARCHAR(100),  -- qBittorrent hash (PRIMARY correlation key)
  download_progress INTEGER DEFAULT 0,
  quality VARCHAR(50),
  indexer VARCHAR(100),
  final_path TEXT,

  -- Shoko (anime)
  shoko_file_id INTEGER,
  shoko_series_id INTEGER,

  -- Display
  poster_url TEXT,

  -- State
  state VARCHAR(20) NOT NULL DEFAULT 'requested',

  -- Metadata
  source VARCHAR(20) DEFAULT 'jellyseerr',  -- 'jellyseerr' or 'library_sync'
  requested_by_user_id INTEGER,
  requested_by_username VARCHAR(100),
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW(),

  -- Indexes
  INDEX idx_state (state),
  INDEX idx_download_id (download_id),
  INDEX idx_tmdb_id (tmdb_id),
  INDEX idx_tvdb_id (tvdb_id),
  INDEX idx_jellyfin_id (jellyfin_id)
);
```

### Deletion Log Table

```sql
CREATE TABLE deletion_log (
  id SERIAL PRIMARY KEY,
  request_id INTEGER REFERENCES media_request(id),

  title VARCHAR(255),
  media_type VARCHAR(10),

  source VARCHAR(20),  -- 'dashboard', 'radarr', 'sonarr', 'jellyfin'
  deleted_by_user_id INTEGER,
  deleted_by_username VARCHAR(100),
  delete_files BOOLEAN,

  -- Sync status per service
  jellyseerr_status VARCHAR(20),
  radarr_status VARCHAR(20),
  sonarr_status VARCHAR(20),
  shoko_status VARCHAR(20),
  jellyfin_status VARCHAR(20),

  initiated_at TIMESTAMP DEFAULT NOW(),
  completed_at TIMESTAMP,

  overall_status VARCHAR(20)  -- 'pending', 'complete', 'partial', 'failed'
);
```

---

## Next Steps

1. [ ] Review this architecture
2. [ ] Identify any missing scenarios
3. [ ] Prioritize implementation order
4. [ ] Start with correlation fix (highest impact)
