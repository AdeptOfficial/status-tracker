# Media Workflow Audit

**Created:** 2026-01-21
**Branch:** fix/media-workflow-audit
**Purpose:** Document all 4 media paths and identify gaps

## Overview

Status-tracker handles 4 distinct media types with different workflows:

| Path | Trigger | Final Transition | Status |
|------|---------|------------------|--------|
| Regular Movies | Radarr → Jellyfin webhook | `jellyfin` | Likely Working |
| Regular TV Shows | Sonarr → Jellyfin webhook | `jellyfin` | Likely Working |
| Anime Movies | Radarr → Shoko → Fallback checker | `jellyfin` | Working (verified) |
| Anime TV Shows | Sonarr → Shoko → ??? | STUCK | **BROKEN** |

---

## Path 1: Regular Movies (Non-Anime)

### Expected Flow
```
Jellyseerr MEDIA_APPROVED
    ↓
REQUESTED → APPROVED (jellyseerr plugin)
    ↓
Radarr Grab webhook
    ↓
INDEXED (radarr plugin)
    ↓
qBittorrent progress polling
    ↓
DOWNLOADING → DOWNLOAD_DONE
    ↓
Radarr Import webhook
    ↓
IMPORTING (radarr plugin)
    ↓
Jellyfin ItemAdded webhook
    ↓
AVAILABLE (jellyfin plugin) ✅
```

### Key Files
- `app/plugins/radarr.py` - Handles Grab/Import
- `app/plugins/jellyfin.py` - Handles ItemAdded webhook

### How AVAILABLE is Reached
Jellyfin webhook plugin (`jellyfin.py:140-148`) transitions to AVAILABLE when:
- `NotificationType == "ItemAdded"`
- `ItemType == "Movie"`
- Request found by TMDB ID correlation

### Potential Issues
1. Jellyfin webhook plugin must be installed and configured
2. If webhook doesn't fire, request stays in IMPORTING indefinitely
3. No fallback mechanism for non-anime movies

### Verification Needed
- [ ] Test end-to-end with a non-anime movie
- [ ] Confirm Jellyfin webhook fires reliably

---

## Path 2: Regular TV Shows (Non-Anime)

### Expected Flow
```
Jellyseerr MEDIA_APPROVED
    ↓
REQUESTED → APPROVED (jellyseerr plugin)
    ↓
Sonarr Grab webhook
    ↓
INDEXED (sonarr plugin)
    ↓
qBittorrent progress polling
    ↓
DOWNLOADING → DOWNLOAD_DONE
    ↓
Sonarr Import webhook
    ↓
IMPORTING (sonarr plugin)
    ↓
Jellyfin ItemAdded webhook (Episode)
    ↓
AVAILABLE (jellyfin plugin) ✅
```

### Key Files
- `app/plugins/sonarr.py` - Handles Grab/Import
- `app/plugins/jellyfin.py` - Handles ItemAdded webhook

### How AVAILABLE is Reached
Same as movies - Jellyfin webhook for Episodes (`ItemType == "Episode"`).

### Potential Issues
1. Same webhook reliability concerns as movies
2. Per-episode vs season pack tracking (separate issue)

### Verification Needed
- [ ] Test end-to-end with a non-anime TV show
- [ ] Confirm Jellyfin webhook fires for episodes

---

## Path 3: Anime Movies

### Expected Flow
```
Jellyseerr MEDIA_APPROVED
    ↓
REQUESTED → APPROVED (jellyseerr plugin)
    ↓
Radarr Grab webhook
    ↓
INDEXED (radarr plugin)
    ↓
qBittorrent progress polling
    ↓
DOWNLOADING → DOWNLOAD_DONE
    ↓
Radarr Import webhook (stores final_path)
    ↓
IMPORTING (radarr plugin)
    ↓
Shoko FileMatched SignalR event
    ↓
ANIME_MATCHING (shoko plugin - if no cross-refs yet)
    OR
AVAILABLE (shoko plugin - if cross-refs exist) [not reliable]
    ↓
Fallback checker polls Jellyfin by TMDB ID
    ↓
AVAILABLE (jellyfin service) ✅
```

### Key Files
- `app/plugins/radarr.py` - Handles Grab/Import
- `app/plugins/shoko.py` - Handles FileMatched SignalR events
- `app/services/jellyfin_verifier.py` - Fallback checker (polls every 30s)
- `app/clients/jellyfin.py` - `find_item_by_tmdb()` lookup

### How AVAILABLE is Reached

**Primary Path (shoko.py:122-140):**
If Shoko sends `FileMatched` with `has_cross_references=True`, transitions directly to AVAILABLE.

**Fallback Path (jellyfin_verifier.py:146-273):**
Every 30 seconds, checks for movies stuck in ANIME_MATCHING or IMPORTING:
```python
stmt = select(MediaRequest).where(
    MediaRequest.state.in_([RequestState.ANIME_MATCHING, RequestState.IMPORTING]),
    MediaRequest.media_type == "movie",  # <-- ONLY MOVIES
    MediaRequest.tmdb_id.isnot(None),
)
```
Then calls `find_item_by_tmdb()` to verify in Jellyfin.

### Current Status: WORKING (per DIARY)
The fallback checker successfully catches anime movies that don't get the Shoko cross-ref event.

### Remaining Concerns
1. Relies on TMDB ID being present
2. 30-second polling adds latency
3. Shoko direct transition doesn't verify Jellyfin availability

---

## Path 4: Anime TV Shows (BROKEN)

### Expected Flow
```
Jellyseerr MEDIA_APPROVED
    ↓
REQUESTED → APPROVED (jellyseerr plugin)
    ↓
Sonarr Grab webhook
    ↓
INDEXED (sonarr plugin)
    ↓
qBittorrent progress polling
    ↓
DOWNLOADING → DOWNLOAD_DONE
    ↓
Sonarr Import webhook (stores final_path)
    ↓
IMPORTING (sonarr plugin)
    ↓
Shoko FileMatched SignalR event
    ↓
ANIME_MATCHING (shoko plugin)
    ↓
??? NO FALLBACK CHECKER FOR TV SHOWS ???
    ↓
STUCK ❌
```

### Key Files
- `app/plugins/sonarr.py` - Handles Grab/Import
- `app/plugins/shoko.py` - Handles FileMatched SignalR events
- `app/services/jellyfin_verifier.py` - **ONLY CHECKS MOVIES**

### Why It's Broken

**Root Cause 1: Fallback checker filters out TV shows**
```python
# jellyfin_verifier.py:173
MediaRequest.media_type == "movie",  # TV shows EXCLUDED
```

**Root Cause 2: No TVDB lookup method**
The fallback checker uses `find_item_by_tmdb()` which searches by TMDB ID.
TV shows use TVDB IDs for correlation with Jellyfin.
There is no `find_item_by_tvdb()` method.

**Root Cause 3: Jellyfin webhook unreliable for Shokofin content**
Per DIARY: "Jellyfin's ItemAdded webhook doesn't fire reliably for Shokofin content"

### What Happens
1. Sonarr imports anime TV show
2. Shoko detects file, sends FileMatched
3. Request transitions to ANIME_MATCHING
4. Fallback checker skips it (media_type != "movie")
5. Jellyfin webhook doesn't fire (Shokofin issue)
6. Request stays in ANIME_MATCHING forever

---

## Required Fixes

### Fix 1: Extend Fallback Checker for TV Shows

**File:** `app/services/jellyfin_verifier.py`

**Changes needed:**
1. Remove `media_type == "movie"` filter (or add `media_type == "tv"`)
2. For TV shows, use TVDB ID instead of TMDB ID
3. Add `find_item_by_tvdb()` method to jellyfin client

**Proposed logic:**
```python
# Check if movie or TV
if request.media_type == "movie" and request.tmdb_id:
    jellyfin_item = await jellyfin_client.find_item_by_tmdb(request.tmdb_id, "Movie")
elif request.media_type == "tv" and request.tvdb_id:
    jellyfin_item = await jellyfin_client.find_item_by_tvdb(request.tvdb_id, "Series")
```

### Fix 2: Add TVDB Lookup to Jellyfin Client

**File:** `app/clients/jellyfin.py`

**Add method:**
```python
async def find_item_by_tvdb(self, tvdb_id: int) -> Optional[dict]:
    """Find a Jellyfin Series by TVDB ID."""
    # Similar to find_item_by_tmdb but:
    # - AnyProviderIdEquals: f"Tvdb.{tvdb_id}"
    # - IncludeItemTypes: "Series"
```

### Fix 3: Consider Unified Fallback Approach

Instead of separate movie/TV logic, consider:
1. Query all stuck requests (ANIME_MATCHING, IMPORTING) regardless of type
2. Determine lookup method based on available IDs:
   - Has TMDB ID + type=movie → TMDB lookup
   - Has TVDB ID + type=tv → TVDB lookup
   - Has both → Try both

---

## Testing Plan

### Pre-implementation Testing
1. [ ] Request a non-anime movie, verify full flow
2. [ ] Request a non-anime TV show, verify full flow
3. [ ] Request an anime movie, verify fallback checker works
4. [ ] Request an anime TV show, confirm it gets stuck

### Post-implementation Testing
1. [ ] Anime TV show reaches AVAILABLE via fallback checker
2. [ ] Anime movie still works
3. [ ] Non-anime content unaffected
4. [ ] Verify jellyfin_id populated correctly for all types

---

## Summary

| Path | Issue | Fix Required |
|------|-------|--------------|
| Regular Movies | Likely working | Verify only |
| Regular TV Shows | Likely working | Verify only |
| Anime Movies | Working | None (already fixed) |
| Anime TV Shows | **BROKEN** | Extend fallback checker + add TVDB lookup |

**Priority:** High - Anime TV shows completely broken
**Effort:** Medium - 2 files to modify, clear pattern from movie implementation

---

## Bugs Found During Testing (2026-01-21)

### Bug 1: Library Sync Creates Phantom Requests

**Discovered:** During anime movie test with "Solo Leveling -ReAwakening-"

**Symptoms:**
- User requests a movie via Jellyseerr
- Status-tracker shows TWO timeline events:
  1. "Ready to Watch" via `library_sync` (BEFORE the user request)
  2. "Approved" via `jellyseerr` (the actual user request)

**Root Cause:** Movie was already in Jellyfin library. `library_sync` detected it and created/updated a request entry before the user even made a request.

**Questions:**
- Should library_sync create requests for items the user didn't explicitly request?
- How should we handle duplicate detection when user requests something already available?
- Is this the intended behavior or a bug?

**Status:** Needs investigation


### Bug 2: Anime Compilation Movies Get Mismatched

**Discovered:** During anime movie test with "Violet Evergarden: Recollections"

**Symptoms:**
- Movie requested via Jellyseerr with TMDB ID 1052946 (movie)
- Radarr downloads file with "(Movie)" in filename
- Shoko matches to AniDB ID 12138 (TV series "Violet Evergarden")
- Shokofin presents it as TV series episodes, not as a movie
- Fallback checker searches for `Movie` with TMDB 1052946 → never finds it

**Root Cause:** 
AniDB categorizes compilation/recap movies as "specials" of the parent TV series rather than standalone movie entries. Shoko follows AniDB's categorization.

**Impact:**
- Anime compilation movies will get stuck in `anime_matching` indefinitely
- The TMDB IDs don't match between Jellyseerr (movie) and Shokofin (TV series)

**Potential Fixes:**
1. Add AniDB ID lookup as alternative to TMDB for anime
2. Fall back to file path matching when TMDB search fails
3. Accept this as a limitation of Shoko's AniDB-based matching

**Status:** Monitoring - waiting to see if Jellyfin eventually picks it up


---

## Test Case 1: Anime Movie - Violet Evergarden: Recollections (2021)

**Date:** 2026-01-21
**Result:** FAILED - Stuck at `anime_matching`

### Timeline Captured

| Time | Service | Event | State |
|------|---------|-------|-------|
| 18:11:58 | Jellyseerr | `MEDIA_AUTO_APPROVED` | `requested → approved` |
| 18:12:05 | Radarr | `Grab` webhook | `approved → indexed` |
| 18:12:08 | qBittorrent | Polling started | `indexed → downloading` |
| 18:15:49 | Radarr | `Import` webhook | `downloading → importing` |
| 18:15:52 | Fallback checker | Not in Jellyfin | `importing → anime_matching` |
| 18:16:04 | Shoko SignalR | `FileMatched` (cross-refs: False) | (already anime_matching) |
| 18:16:04+ | Shoko SignalR | `FileHashed`, `SeriesUpdated`, `EpisodeUpdated` | (not handled) |
| ∞ | Fallback checker | Polling every 30s, never finds match | **STUCK** |

### Root Cause: Architecture Conflict

**Different systems categorize the same content differently:**

| System | View | ID |
|--------|------|-----|
| Jellyseerr/TMDB | Movie: "Violet Evergarden: Recollections" | TMDB 1052946 |
| Radarr | Movie → stores in `/anime/movies/` | TMDB 1052946 |
| Shoko/AniDB | TV Series Special: "Violet Evergarden" | AniDB 12138 |
| Shokofin VFS | TV Series episodes | TMDB Show 75214 |
| Jellyfin | Shows in "Anime Shows", not "Anime Movies" | N/A |

**Fallback checker searches:** `GET /Items?IncludeItemTypes=Movie&AnyProviderIdEquals=Tmdb.1052946`
**Jellyfin has:** TV Series with TMDB Show 75214
**Result:** No match, request stuck forever

### Why This Happens

1. **Compilation/recap movies** are often categorized as "specials" in AniDB
2. Shoko follows AniDB's categorization, not the file path
3. Shokofin creates VFS based on Shoko's view
4. Physical folder (`/anime/movies/`) is irrelevant to Shokofin VFS
5. TMDB movie ID ≠ TMDB show ID → lookup fails

### Shoko SignalR Events Observed

```
ShokoEvent:FileHashed      - NOT HANDLED
ShokoEvent:FileMatched     - HANDLED (but cross-refs: False)
ShokoEvent:SeriesUpdated   - NOT HANDLED  
ShokoEvent:EpisodeUpdated  - NOT HANDLED (many instances)
ShokoEvent:FileDeleted     - NOT HANDLED
```

### Potential Fixes

1. **Path-based fallback:** If TMDB lookup fails, search by file path or title
2. **Accept TMDB show ID:** For anime, try both movie and show TMDB IDs
3. **Shoko config:** Investigate if Shoko can be configured to treat certain content as movies
4. **Manual override:** Allow users to manually mark requests as available
5. **Document as limitation:** Compilation movies may not work with Shoko pipeline

### Status

**DOCUMENTED** - Moving to Test Case 1b with standalone anime movie (Chainsaw Man: Reze Arc)


---

## Test Case 1b: Anime Movie - Chainsaw Man: Reze Arc (2025)

**Date:** 2026-01-21
**Result:** FAILED - Correlation bug

### Timeline

| Time | Service | Event | Issue |
|------|---------|-------|-------|
| 18:50:03 | Jellyseerr | `MEDIA_AUTO_APPROVED` | Created request **14** ✅ |
| 18:50:10 | Radarr | `Grab` | Matched to request **11** ❌ |
| 18:50:10 | State machine | Transition failed | `available -> indexed` invalid |
| 18:55:49 | Radarr | `Import` | Also matched wrong request |

### Root Cause

**Correlation matches wrong request** when multiple requests exist for the same TMDB ID.

- Request 11 (old, already `available`) has same TMDB ID
- Radarr webhook correlates by TMDB ID
- Finds request 11 first, ignores request 14
- State machine rejects invalid transition
- New request 14 stuck at `approved` forever

### Bug 3: Correlation Priority Issue

The correlator doesn't prioritize:
- Most recent request
- Requests in "active" states (not already available)
- The request that actually triggered the download

---

## Bugs Summary (2026-01-21)

| # | Bug | Impact |
|---|-----|--------|
| 1 | Library sync phantom requests | Creates requests user didn't make |
| 2 | Compilation movies Shoko mismatch | Stuck at anime_matching |
| 3 | Correlation matches wrong request | State updates go to wrong request |
| 4 | Poster URL missing | No poster on dashboard |

---

## Recommendation: Replan the Flow

The current architecture has fundamental issues:

1. **Correlation is too loose** - TMDB ID alone isn't sufficient
2. **No request lifecycle isolation** - Old and new requests interfere
3. **State machine doesn't handle edge cases** - Invalid transitions silently fail
4. **Multiple systems disagree on content type** - Shoko vs Jellyseerr

**Suggested approach:**
1. Document the INTENDED flow for each path
2. Identify where correlation should happen and with what priority
3. Define clear state transition rules
4. Handle duplicate/concurrent requests explicitly

