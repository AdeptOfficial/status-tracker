# Session Memory: Status-Tracker UI Bugs, SSE, and Shoko VFS Fixes

**Date:** 2026-01-25
**Status:** Ready to Deploy

---

## Context

Testing status-tracker workflow with anime movie "The Garden of Words" (2013). Found and fixed multiple UI bugs and workflow issues.

## Security Protocols (CRITICAL)

From `/home/adept/git/homeserver/CLAUDE.md`:
- **NEVER** read `.env`, `config.xml`, `settings.json` without explicit request
- **NEVER** run `printenv`, `env`, `docker inspect`, `docker-compose config`
- **NEVER** SSH into servers unless user explicitly asks
- If credentials found: STOP, notify user, create issue

## Dev Environment

- **Proxmox host:** 10.0.2.10
- **Media-dev LXC:** 10.0.2.20 (VMID 220)
- **Status-Tracker:** http://10.0.2.20:8100
- **Deploy script:** `/home/adept/git/status-tracker-workflow-fix/scripts/deploy.sh`

---

## Completed Fixes (NOT YET DEPLOYED)

### 1. "Importing:" Label Fix ✅ TESTED & VERIFIED

**Files changed:**
- `app/plugins/sonarr.py` (lines 318, 320, 382)
- `app/plugins/radarr.py` (lines 236, 307)

**Change:** "Imported:" → "Importing:" for consistency with state label

**Verified:** Timeline showed `Importing: [RAI] The Garden of Words...`

### 2. Active Requests Counter Shows "0" ✅ FIXED

**File:** `app/templates/index.html`

**Problem:** Counter was OUTSIDE `#request-list` div, so htmx refresh only updated cards, not counter.

**Fix:** Restructured HTML to include counter INSIDE the refreshable `#request-list` div.

### 3. Download Size Shows "0 B" ✅ FIXED

**File:** `app/plugins/qbittorrent.py` (line 284-291)

**Problem:** During `metaDL` state, `torrent.size` is 0.

**Fix:** Check if size > 0, else show "fetching metadata..."

```python
if torrent.size and torrent.size > 0:
    size_text = format_size(torrent.size)
else:
    size_text = "fetching metadata..."
```

### 4. SSE Error Logging ✅ ADDED

**File:** `app/core/broadcaster.py` (line 113-126)

**Problem:** `broadcast_update` might fail silently during serialization.

**Fix:** Wrapped in try/except with `logger.error(..., exc_info=True)`

### 5. Shoko VFS Detection Delay ✅ FIXED

**Root Cause Found:**
- Shoko FileMatched arrives with `cross-refs: False` (too early)
- Immediate verification skipped
- Fallback only kicks in after 2 min (`STUCK_THRESHOLD_MINUTES`)
- Total delay: ~4 minutes

**Files changed:**
- `app/clients/shoko.py` - Rewrote `_handle_movie_updated()` to handle `Reason: 'Added'` events
- `app/services/jellyfin_verifier.py` - Added `verify_movie_by_tmdb()` function

**New flow:**
1. Shoko sends `MovieUpdated` with `Reason: 'Added'`, `MovieID: <tmdb_id>`
2. Handler triggers library scan
3. Waits 10s for VFS regeneration
4. Finds request by TMDB ID
5. Verifies in Jellyfin → AVAILABLE

**Expected improvement:** ~15-20 seconds instead of ~4 minutes

---

## Issues Files Created

| File | Description |
|------|-------------|
| `issues/2026-01-25-active-requests-counter-wrong.md` | Counter bug |
| `issues/2026-01-25-download-size-shows-zero.md` | 0 B bug |
| `issues/2026-01-25-sse-live-updates-broken.md` | SSE regression |
| `issues/2026-01-25-anime-matching-details-mismatch.md` | UX: "Matching" state shows "Importing:" |
| `issues/2026-01-25-anime-vfs-jellyfin-detection.md` | VFS delay |

## Feature Request Created

- `features/display-original-title.md` - Show Japanese title alongside English (helps debug indexer issues)

---

## Pending Issues (Not Fixed This Session)

### SSE Live Updates Not Refreshing

**Status:** Investigated but root cause unclear

**Findings:**
- Backend IS broadcasting: `broadcast_update called: request_id=4...`
- 1 client connected (verified via `/api/sse/status`)
- BUT: Don't see "Broadcasting 'update' to X clients" log after

**Added:** Error logging to catch serialization failures. Need to redeploy and test.

### UX: Anime Matching Shows "Importing:" Details

**File:** `issues/2026-01-25-anime-matching-details-mismatch.md`

**Issue:** State label says "Matching" but details say "Importing: filename"

**Low priority** - technically correct, just confusing

---

## Test Results

**Test Movie:** The Garden of Words (2013) - 46 min anime movie

**Full Flow:**
```
06:39:41 - Approved (auto)
06:39:48 - Grabbed (Bluray-1080p from Nyaa.si)
06:39:49 - Downloading (0 B bug visible)
06:42:09 - Downloaded (4.41 GB)
06:42:50 - Matching/Importing (verified "Importing:" fix)
06:46:09 - Available (via fallback after ~4 min)
```

---

## Files Changed (Summary)

```
app/templates/index.html          # Counter inside refresh area
app/plugins/qbittorrent.py        # "fetching metadata..." for 0 B
app/plugins/sonarr.py             # "Importing:" label
app/plugins/radarr.py             # "Importing:" label
app/core/broadcaster.py           # SSE error logging
app/clients/shoko.py              # MovieUpdated "Added" handler
app/services/jellyfin_verifier.py # verify_movie_by_tmdb() function
```

---

## Next Steps

1. **Deploy all fixes:**
   ```bash
   cd /home/adept/git/status-tracker-workflow-fix && ./scripts/deploy.sh
   ```

2. **Test with new anime request** to verify:
   - Counter updates correctly
   - Download size shows properly
   - Shoko VFS detection is faster (~15-20s)
   - SSE logs show any errors

3. **If SSE still broken:** Check browser console for JS errors, check server logs for serialization errors

---

## Key Constants (Reference)

```python
# jellyfin_verifier.py
INITIAL_DELAY_SECONDS = 10
RETRY_DELAY_SECONDS = 15
MAX_RETRIES = 3
STUCK_THRESHOLD_MINUTES = 2
VFS_REGENERATION_DELAY = 10
```

---

## Resume Prompt

```
Continue status-tracker testing from session `.claude/memory/session-2026-01-25-ui-bugs-sse-shoko.md`

Working directory: /home/adept/git/status-tracker-workflow-fix

STATUS: Ready to deploy fixes

COMPLETED FIXES (not yet deployed):
1. "Importing:" label fix (sonarr.py, radarr.py) - TESTED
2. Counter shows 0 fix (index.html)
3. Download "0 B" fix (qbittorrent.py)
4. SSE error logging (broadcaster.py)
5. Shoko VFS delay fix (shoko.py, jellyfin_verifier.py)

SECURITY: Do NOT read .env, config.xml, or run env/printenv. Ask before SSH.

NEXT ACTION: Deploy with `./scripts/deploy.sh` and test with a new anime request.

OPEN ISSUE: SSE might still not refresh UI - added logging to debug. Check logs after deploy.
```
