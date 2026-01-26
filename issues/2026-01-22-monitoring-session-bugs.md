# Bugs Found During Live Monitoring Session

**Date:** 2026-01-22
**Test:** Lycoris Recoil (Anime TV, Season 1, 13 episodes)

## Critical Issues

### 1. Missing `/api/requests/{id}/episodes` Endpoint
**Status:** Fix prepared, awaiting deployment
**Impact:** Frontend cannot display per-episode status for TV shows

**Details:**
- API returns 404 for `/api/requests/1/episodes`
- Episodes ARE created in DB during Sonarr Grab (confirmed: "13 episodes" logged)
- Missing: `EpisodeResponse` schema in `schemas.py`
- Missing: Endpoint in `app/routers/api.py`

**Fix:** Already implemented locally, needs deployment.

---

### 2. Sonarr Auto-Import Not Working
**Status:** Configuration issue
**Impact:** Downloads complete but Sonarr doesn't import automatically

**Details:**
- qBittorrent marked download as complete (state → `downloaded`)
- Sonarr Queue showed empty - didn't detect completed download
- Sonarr Wanted still showed all 13 episodes as "Missing"
- Required manual import via Sonarr UI

**Root Cause:** Likely category mismatch between Sonarr's configured category and qBittorrent's actual category for the download.

**Fix:** Check Sonarr Settings → Download Clients → Category matches qBittorrent.

---

### 3. Manual Import Doesn't Trigger Webhook
**Status:** Bug or configuration issue
**Impact:** State stuck at `downloaded` after manual import

**Details:**
- User performed manual import in Sonarr
- No "Download" (Import) webhook received by status-tracker
- State remains `downloaded`, never transitions to `IMPORTING`

**Possible Causes:**
1. Sonarr webhook didn't have "On File Import" enabled (was only "On Import Complete")
2. Manual imports may not trigger webhooks (Sonarr behavior?)

**Configuration Found:**
- Webhook URL was correct: `http://status-tracker:8000/hooks/sonarr`
- "On Grab" ✅ enabled
- "On File Import" ❌ was NOT enabled (added during debugging)
- "On Import Complete" ✅ enabled

**Fix:**
1. Verify Sonarr webhook has "On Import" event enabled
2. Consider adding fallback: poll Sonarr API to detect imported episodes

---

### 4. SQLite Database Locking
**Status:** Concurrency bug
**Impact:** Intermittent errors, potential data loss

**Details:**
```
ERROR - Jellyfin fallback checker error: (sqlite3.OperationalError) database is locked
```

**Root Cause:** Multiple async operations accessing SQLite concurrently (qBit polling, fallback checker, webhook handlers).

**Fix Options:**
1. Add connection pooling with proper timeout/retry
2. Use WAL mode for SQLite
3. Migrate to PostgreSQL for production

---

### 5. `is_anime` Not Detected (Showing `None`)
**Status:** Code bug
**Impact:** Anime flow routing broken - doesn't go through ANIME_MATCHING

**Details:**
- Lycoris Recoil is tagged as "Anime" in Sonarr (series.type = "Anime")
- After Sonarr Grab webhook, `is_anime` was `None` instead of `True`
- API confirmed: `"is_anime": null`
- This breaks the entire anime workflow routing

**Root Cause:** The `series.type` field extraction in `sonarr.py` may not be working correctly, or the field name differs from expected.

**Fix:** Debug `sonarr.py` Grab handler - check if `series.get("type")` returns the expected value. May need `series.get("seriesType")` instead.

---

### 6. SSE Not Auto-Updating New Requests
**Status:** Frontend/Backend bug
**Impact:** Users must refresh page to see newly created requests

**Details:**
- When a new request is created via Jellyseerr webhook, it doesn't appear in the request list
- User had to manually refresh the page to see the new request
- SSE connection is working (shows client connected/disconnected in logs)
- Issue is specifically with NEW request notifications, not updates

**Fix:** Ensure `broadcaster.broadcast_update()` is called after new request creation, or add a separate `broadcast_new_request()` event type.

---

### 7. GRABBING State Appears Late
**Status:** Expected behavior / UX issue
**Impact:** User sees "Approved" for extended period, then GRABBING appears briefly before DOWNLOADING

**Details:**
- After request is approved, user sees "Approved" state for 2+ minutes
- GRABBING state only appears once Sonarr sends Grab webhook
- This happens after Sonarr searches all indexers and grabs release
- Gap between Approved → GRABBING is Sonarr search time, not status-tracker delay

**Potential Improvements:**
1. Add intermediate "Searching..." state when Sonarr starts searching
2. Poll Sonarr API to detect search activity
3. Show "Waiting for Sonarr..." indicator in UI

---

### 8. Shoko FileMatched Logs Show Empty Filename
**Status:** Logging bug
**Impact:** Hard to debug which files Shoko is processing

**Details:**
```
app.clients.shoko - INFO - Shoko file matched:  (cross-refs: False)
```
- The filename/path is empty in the log message
- Should show: `Shoko file matched: Season 1/Lycoris.Recoil.S01E01.mkv (cross-refs: False)`

**Fix:** Check `shoko.py` client - ensure `event.relative_path` is being passed to the log statement.

---

## Missing Shoko Event Handlers

The following Shoko SignalR events are received but not handled:

| Event | Count | Notes |
|-------|-------|-------|
| `ShokoEvent:FileDetected` | 13 | Files detected in watch folder |
| `ShokoEvent:FileHashed` | Many | Files being hashed |
| `ShokoEvent:FileDeleted` | Many | Cleanup events |
| `ShokoEvent:SeriesUpdated` | 1+ | Series metadata updated |
| `ShokoEvent:OnConnected` | 1 | Initial connection |

**Impact:**
- `FileDetected` could trigger IMPORTING state as fallback
- Missing events means less visibility into Shoko processing

**Currently Handled:**
- `FileMatched` - but all showed `cross-refs: False` (AniDB matching pending)

---

## Flow Gap: No Fallback for Stuck `downloaded` State

**Problem:** If Sonarr Import webhook never arrives, request stays stuck at `downloaded` forever.

**Potential Solutions:**
1. **Poll Sonarr API** - Check if episodes have files assigned
2. **Use Shoko FileDetected** - Transition to IMPORTING when Shoko sees files
3. **Timeout + retry** - After X minutes in `downloaded`, check Sonarr/Jellyfin
4. **Jellyfin fallback** - Already exists but only checks IMPORTING/ANIME_MATCHING states

---

## Timeline of Test

| Time | Event |
|------|-------|
| 00:12:01 | Jellyseerr webhook - request created |
| 00:14:35 | Sonarr Grab - 13 episodes, **is_anime=None (BUG!)** |
| 00:15:04 | qBittorrent - downloading started |
| 00:27:18 | qBittorrent - download complete (31.58 GB) |
| 00:27:18+ | **STUCK** - waiting for Sonarr Import |
| 00:32:25 | Manual import performed |
| 00:32:25 | Shoko FileDetected × 13 |
| 00:32:39+ | Shoko FileMatched (cross-refs: False) |
| 00:33:34 | Last Shoko activity |

| 00:35:01 | Shoko matched to AniDB (AnimeID: 17097) |
| 00:35:01+ | **No FileMatched cross-refs:True received** |
| -- | Jellyfin search returns "Not found" (library not scanned) |

**Final State:** `downloaded` (stuck - missing Import webhook, no Shoko cross-refs signal, Jellyfin not scanned)

---

### 9. Jellyfin Library Not Auto-Scanning After Shoko Import
**Status:** Integration gap
**Impact:** Even when Shoko matches files, Jellyfin doesn't see them until manual scan

**Details:**
- Shoko successfully matched all 13 episodes to AniDB
- Shokofin plugin is installed and watching `/data/anime/shows`
- But Jellyfin `search_by_title('Lycoris Recoil')` returned None
- Library scan last ran at 00:23:42 (before import)

**Root Cause:** Shokofin's real-time file watcher may not trigger library additions, only updates.

**Fix Options:**
1. Trigger Jellyfin library scan via API after Shoko match
2. Configure Shokofin to auto-add new series
3. Add fallback: if Jellyfin search fails, trigger library refresh

---

## Fixes Prepared (Not Deployed)

1. **EpisodeResponse schema** - Added to `app/schemas.py`
2. **Episodes endpoint** - Added to `app/routers/api.py`

Awaiting user confirmation before deployment.
