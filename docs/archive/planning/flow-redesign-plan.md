# Status-Tracker Flow Redesign Plan

**Date:** 2026-01-21
**Purpose:** Map all 4 media paths, identify common/divergent points, fix correlation issues

---

## The 4 Media Paths

| Path | Request Source | Download Manager | Metadata Source | Final Verification |
|------|---------------|------------------|-----------------|-------------------|
| 1. Regular Movie | Jellyseerr | Radarr | TMDB | Jellyfin (TMDB lookup) |
| 2. Regular TV | Jellyseerr | Sonarr | TMDB/TVDB | Jellyfin (TVDB lookup) |
| 3. Anime Movie | Jellyseerr | Radarr | TMDB → Shoko/AniDB | Jellyfin (???) |
| 4. Anime TV | Jellyseerr | Sonarr | TMDB → Shoko/AniDB | Jellyfin (???) |

---

## Common Flow (All 4 Paths)

```
┌─────────────────────────────────────────────────────────────────┐
│                        COMMON ENTRY                              │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  User Request (Jellyseerr)                                       │
│       │                                                          │
│       ▼                                                          │
│  REQUESTED ──webhook──► APPROVED                                 │
│       │                                                          │
│       │  Jellyseerr sends to Radarr/Sonarr                      │
│       ▼                                                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                     ┌───────┴───────┐
                     │               │
                  MOVIE            TV SHOW
                 (Radarr)         (Sonarr)
                     │               │
                     ▼               ▼
```

---

## Path Divergence Point 1: Download Manager

### Movies (Radarr) - Paths 1 & 3

```
Radarr Grab Webhook
    │
    │  Correlation: tmdb_id, download_id (qbit hash)
    │
    ▼
INDEXED
    │
    │  qBittorrent polling (by hash)
    │
    ▼
DOWNLOADING ──progress──► DOWNLOAD_DONE
    │
    │  Radarr Import Webhook
    │
    ▼
IMPORTING
    │
    └──────► DIVERGES HERE (anime vs regular)
```

### TV Shows (Sonarr) - Paths 2 & 4

```
Sonarr Grab Webhook
    │
    │  Correlation: tvdb_id, download_id (qbit hash)
    │
    ▼
INDEXED
    │
    │  qBittorrent polling (by hash)
    │
    ▼
DOWNLOADING ──progress──► DOWNLOAD_DONE
    │
    │  Sonarr Import Webhook
    │
    ▼
IMPORTING
    │
    └──────► DIVERGES HERE (anime vs regular)
```

---

## Path Divergence Point 2: Final Verification

### Path 1: Regular Movie

```
IMPORTING
    │
    │  Jellyfin ItemAdded webhook (Movie)
    │  OR Fallback: Poll Jellyfin by TMDB ID
    │
    ▼
AVAILABLE ✅
```

**Correlation:** TMDB ID
**Jellyfin Search:** `IncludeItemTypes=Movie&AnyProviderIdEquals=Tmdb.{id}`

### Path 2: Regular TV Show

```
IMPORTING
    │
    │  Jellyfin ItemAdded webhook (Episode)
    │  OR Fallback: Poll Jellyfin by TVDB ID  ← MISSING!
    │
    ▼
AVAILABLE ✅
```

**Correlation:** TVDB ID
**Jellyfin Search:** `IncludeItemTypes=Series&AnyProviderIdEquals=Tvdb.{id}` ← NEEDS IMPLEMENTATION

### Path 3: Anime Movie

```
IMPORTING
    │
    ├──► Shoko FileMatched (SignalR)
    │         │
    │         ▼
    │    ANIME_MATCHING
    │         │
    │         │  Fallback: Poll Jellyfin by TMDB ID
    │         │  BUT: Shokofin may use different TMDB ID!
    │         │
    │         ▼
    │    AVAILABLE (if found) or STUCK
    │
    └──► Direct Jellyfin webhook (unreliable for Shokofin)
```

**Issues:**
- Shoko may categorize as TV special → wrong TMDB ID
- Shokofin VFS may not present as "Movie" type
- TMDB lookup fails if IDs don't match

### Path 4: Anime TV Show

```
IMPORTING
    │
    ├──► Shoko FileMatched (SignalR)
    │         │
    │         ▼
    │    ANIME_MATCHING
    │         │
    │         │  Fallback: ??? ← COMPLETELY MISSING!
    │         │  - No TVDB lookup implemented
    │         │  - Fallback checker filters out TV shows
    │         │
    │         ▼
    │    STUCK FOREVER ❌
    │
    └──► Direct Jellyfin webhook (unreliable for Shokofin)
```

**Issues:**
- Fallback checker has `media_type == "movie"` filter
- No `find_item_by_tvdb()` method
- Shoko may use AniDB IDs, not TVDB

---

## Correlation Strategy (Current vs Proposed)

### Current (Broken)

```python
# Correlator finds ANY request matching the ID
request = await correlator.find_by_any(
    db,
    tmdb_id=tmdb_id,  # Finds first match, even if AVAILABLE
    tvdb_id=tvdb_id,
)
```

**Problem:** Returns old completed requests, not the active one.

### Proposed

```python
# Correlator should prioritize:
# 1. Requests in "active" states (not available/deleted)
# 2. Most recently created
# 3. Exact match on download_id if available

request = await correlator.find_active_by_any(
    db,
    tmdb_id=tmdb_id,
    tvdb_id=tvdb_id,
    download_id=download_id,  # qbit hash - most reliable!
    exclude_states=[RequestState.AVAILABLE, RequestState.DELETED],
    order_by="created_at DESC",
)
```

---

## ID Mapping Problem

| Service | Movie ID | TV ID | Anime ID |
|---------|----------|-------|----------|
| Jellyseerr | TMDB | TMDB | TMDB |
| Radarr | TMDB | - | TMDB |
| Sonarr | - | TVDB | TVDB |
| Shoko | - | - | AniDB |
| Shokofin | TMDB (sometimes) | TMDB (sometimes) | AniDB → TMDB mapped |
| Jellyfin | TMDB, IMDB | TVDB, TMDB | Depends on metadata source |

**The ID mismatch is the core problem for anime.**

---

## Proposed Fixes

### Fix 1: Improve Correlator (All Paths)

```python
# Priority order for correlation:
1. download_id (qbit hash) - unique per download
2. tmdb_id + active state
3. tvdb_id + active state
4. title + year (fuzzy fallback)
```

### Fix 2: Add TVDB Lookup (Path 2 & 4)

```python
# In jellyfin_verifier.py - remove movie-only filter
# In jellyfin.py - add find_item_by_tvdb()
```

### Fix 3: Anime Fallback Strategy (Path 3 & 4)

```python
# Try multiple lookup methods:
1. TMDB ID (movie or show)
2. TVDB ID
3. Title search in Jellyfin
4. File path matching
```

### Fix 4: Handle Shoko Mismatch (Path 3 & 4)

```python
# When Shoko categorizes differently:
# - Store both Jellyseerr's TMDB and Shoko's AniDB ID
# - Try both when searching Jellyfin
# - Accept "close enough" matches for anime
```

---

## Implementation Priority

| Priority | Fix | Effort | Impact |
|----------|-----|--------|--------|
| 1 | Fix correlator priority | Medium | Fixes Bug 3 (wrong request) |
| 2 | Add TVDB lookup | Low | Fixes anime TV shows |
| 3 | Remove movie-only filter | Low | Enables TV fallback |
| 4 | Anime fallback strategy | High | Handles Shoko mismatch |
| 5 | Poster URL | Low | Cosmetic |

---

## Next Steps

1. [ ] Fix correlator to prioritize active requests
2. [ ] Add `find_item_by_tvdb()` method
3. [ ] Remove `media_type == "movie"` filter from fallback checker
4. [ ] Test regular TV show flow (should work with fixes 2-3)
5. [ ] Test anime TV show flow
6. [ ] Design anime fallback strategy for Shoko mismatches
