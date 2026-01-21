# Status Tracker: ANIME_MATCHING State Stuck for Movies

**Created:** 2026-01-18
**Updated:** 2026-01-19
**Status:** Implementation Complete - Ready for Testing
**Component:** apps/status-tracker
**Priority:** High
**Feature:** State Machine / Shoko Integration

## Status Update (2026-01-19)

**Original bug is FIXED** - MovieUpdated events now properly trigger transitions.

**NEW ISSUE DISCOVERED:** Status-tracker declares "Ready to Watch" before Jellyfin actually has the movie available.

### Test Results (Rascal Does Not Dream of a Knapsack Kid)

```
01:36:53 - Shoko MovieUpdated "Added" → status-tracker: AVAILABLE ✅
01:37:30 - Jellyfin library scan started (37 seconds later)
01:37:31 - Shokofin VFS: Created 1 new entry (movie appears)
01:37:34 - Scan complete
```

**Gap:** 37 seconds where UI shows "Ready to Watch" but movie not playable.

## Problem

Anime movies transition to AVAILABLE when **Shoko finishes metadata matching**, NOT when **Jellyfin confirms availability**.

### Current Behavior

JJK 0 (Jujutsu Kaisen 0) request flow:
- REQUESTED → APPROVED → INDEXED → DOWNLOADING → DOWNLOAD_DONE → IMPORTING → ANIME_MATCHING → **stuck**
- Movie is visible in Jellyfin (working)
- Status-tracker never reaches AVAILABLE

### Expected Behavior

After Shoko matches the anime movie to AniDB/TMDB, the request should transition to `available`.

## Root Cause Analysis

### The Two Event Types

Shoko sends different events for files vs movies:

1. **FileMatched** (for TV episodes):
   ```json
   {
     "FileId": 108,
     "RelativePath": "anime/movies/JJK0/movie.mkv",
     "HasCrossReferences": true
   }
   ```

2. **MovieUpdated** (for anime movies):
   ```json
   {
     "Source": "TMDB",
     "Reason": "Added",
     "MovieID": 810693,
     "ShokoEpisodeIDs": [330],
     "ShokoSeriesIDs": [15]
   }
   ```

### The Bug

The `_handle_movie_updated` function in `app/clients/shoko.py` expects a `RelativePath` field to correlate with the request:

```python
# Line 253-262
relative_path=file_info.get("RelativePath", file_info.get("relativePath", ""))
...
if event.relative_path:
    await self._dispatch_file_matched(event)
else:
    logger.debug(f"MovieUpdated event missing path...")  # Silently skipped!
```

**MovieUpdated events don't contain `RelativePath`** - they have TMDB/Shoko IDs instead. The correlation fails silently.

### Log Evidence

```
22:39:09 - Shoko file matched:  (cross-refs: False)  # FileMatched → ANIME_MATCHING
22:39:13 - Movie updated event received: [{'Source': 'TMDB', 'Reason': 'Added', 'MovieID': 810693, ...}]
# ^^^ These events have no path, so they're silently ignored
```

## Proposed Design Change (2026-01-19)

**Goal:** Only mark as AVAILABLE when Jellyfin confirms the movie is playable.

### New Flow

```
ANIME_MATCHING (Shoko FileMatched)
    ↓
Shoko MovieUpdated "Added" received
    ↓
Trigger Jellyfin library scan (targeted to Anime Movies library)
    ↓
Stay in ANIME_MATCHING, wait for Jellyfin
    ↓
Jellyfin detects movie via Shokofin VFS
    ↓
Jellyfin sends ItemAdded webhook
    ↓
AVAILABLE (via jellyfin) ✅
```

### Implementation Options

**Option A: Trigger Scan + Rely on Webhook (Recommended)**

```python
# app/plugins/shoko.py - handle_shoko_movie_available()

async def handle_shoko_movie_available(event: "MovieAvailableEvent", db: "AsyncSession"):
    """Don't mark available yet - wait for Jellyfin."""

    # Find request
    request = await find_request_by_tmdb_id(event.tmdb_id, db)
    if not request:
        return

    # Store Shoko series ID for tracking
    if event.shoko_series_id:
        request.shoko_series_id = event.shoko_series_id

    # Trigger Jellyfin library scan (async, non-blocking)
    from app.clients.jellyfin import jellyfin_client
    await jellyfin_client.trigger_library_scan()

    # Log but DON'T transition yet
    logger.info(
        f"Shoko matched {request.title}, triggered Jellyfin scan. "
        f"Waiting for Jellyfin to confirm availability..."
    )

    # Jellyfin ItemAdded webhook will handle transition to AVAILABLE
    await db.commit()
```

**Pros:**
- Simple - uses existing Jellyfin webhook infrastructure
- No polling overhead
- Jellyfin plugin already has the logic to transition to AVAILABLE

**Cons:**
- If webhook never comes, request stays stuck
- Need timeout/fallback mechanism

**Option B: Active Polling**

Add polling service that checks Jellyfin API every 10 seconds for 5 minutes:

```python
async def wait_for_jellyfin_availability(request: MediaRequest, db: AsyncSession):
    """Poll Jellyfin until movie appears."""
    max_attempts = 30  # 5 minutes

    for attempt in range(max_attempts):
        # Search Jellyfin for movie by TMDB ID
        items = await jellyfin_client.get_all_items(
            include_types=["Movie"],
            fields=["ProviderIds"]
        )

        for item in items:
            if item.get("ProviderIds", {}).get("Tmdb") == str(request.tmdb_id):
                # Found it! Transition to AVAILABLE
                await state_machine.transition(
                    request,
                    RequestState.AVAILABLE,
                    db,
                    service="jellyfin",
                    event_type="Detected",
                    details="Available in library"
                )
                return True

        await asyncio.sleep(10)

    # Timeout - log warning
    logger.warning(f"Timeout waiting for {request.title} in Jellyfin")
    return False
```

**Pros:**
- Guaranteed detection (with timeout)
- More reliable than relying on webhooks

**Cons:**
- Polling overhead
- More complex implementation

### Recommendation

**Use Option A** (Trigger Scan + Webhook) with these safeguards:

1. Trigger targeted library scan when Shoko finishes
2. Rely on existing Jellyfin ItemAdded webhook
3. Add timeout fallback: If still ANIME_MATCHING after 10 minutes, log error for investigation
4. Timeline shows "Waiting for Jellyfin sync..." so users understand the delay

## Acceptance Criteria

### Phase 1: Original Bug (COMPLETE ✅)
- [x] Anime movies transition from `anime_matching` to `available`
- [x] MovieUpdated events are correlated by TMDB ID
- [x] Shoko series ID is stored in request for future use
- [x] Log at INFO level when MovieUpdated triggers state change

### Phase 2: Jellyfin Verification (IMPLEMENTED ✅)
- [x] Shoko MovieUpdated "Added" triggers Jellyfin library scan
- [x] Request stays in ANIME_MATCHING until Jellyfin confirms
- [x] Jellyfin ItemAdded webhook transitions to AVAILABLE (not Shoko)
- [x] Timeline shows "via jellyfin" for final transition
- [x] No "Ready to Watch" until Jellyfin has the movie
- [ ] ~~Timeline shows intermediate "Waiting for Jellyfin sync..." message~~ (deferred - logs show status)
- [ ] ~~Targeted library scan (Anime Movies only, not full scan)~~ (deferred - full scan is acceptable)

### Implementation Summary (2026-01-19 01:48)

**Changes Made:**
- Modified `app/plugins/shoko.py:219-273` - `handle_shoko_movie_available()`
  - Removed transition to AVAILABLE
  - Added call to `jellyfin_client.trigger_library_scan()`
  - Added logging for scan success/failure
  - Request now stays in ANIME_MATCHING state

**How It Works:**
1. Shoko sends MovieUpdated "Added" event
2. Shoko plugin finds request by TMDB ID
3. Stores Shoko series ID
4. **Triggers Jellyfin library scan** (via `/Library/Refresh` API)
5. Logs: "Shoko matched, triggered Jellyfin scan, waiting for ItemAdded webhook..."
6. Request stays in ANIME_MATCHING
7. Jellyfin scans library, Shokofin VFS exposes movie
8. Jellyfin sends ItemAdded webhook
9. Existing Jellyfin plugin handles webhook → AVAILABLE (via jellyfin) ✅

**Container restarted:** 2026-01-19 01:48:55

## Affected Files

- `app/clients/shoko.py` - Event parsing and dispatch
- `app/plugins/shoko.py` - State transition logic
- `app/models.py` - May need `shoko_series_id` field

## Test Case

1. Request an anime movie (e.g., Jujutsu Kaisen 0)
2. Wait for download and import
3. Verify Shoko matches the file
4. Verify status-tracker transitions to AVAILABLE (currently fails)
