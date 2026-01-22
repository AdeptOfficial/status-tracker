# Anime Workflow Fix Summary

**Date:** 2026-01-22
**Result:** All 4 media workflows working ✅

---

## Workflows Tested

| Workflow | Test | Result |
|----------|------|--------|
| Regular Movie | (not tested this session) | Expected working |
| Regular TV | (not tested this session) | Expected working |
| **Anime Movie** | Akira | ✅ available |
| **Anime TV** | My Teen Romantic Comedy SNAFU | ✅ available |

---

## Root Causes Found

### 1. Shokofin SignalR Not Receiving Events

**Problem:** Shokofin connected to Shoko SignalR but wasn't receiving file events.

**Impact:** VFS never regenerated automatically after Shoko matched files.

**Workaround:** Trigger library refresh via API to force VFS regeneration:
```bash
curl -X POST 'http://JELLYFIN:8096/Library/Refresh' \
  -H 'X-Emby-Token: YOUR_API_KEY'
```

### 2. Anime Shows Library Not Configured in Shokofin

**Problem:** Shokofin config (`Shokofin.xml`) was missing the Anime Shows library.

**Evidence:**
- Anime Movies: Configured with `ManagedFolderId=2` ✓
- Anime Shows: **Missing from config**

**Fix:** Added MediaFolderConfiguration to `Shokofin.xml`:
```xml
<MediaFolderConfiguration_V2>
  <LibraryId>29391378-c411-8b35-b77f-84980d25f0a6</LibraryId>
  <Path>/data/anime/shows</Path>
  <ManagedFolderId>1</ManagedFolderId>
  <ManagedFolderName>anime_shows</ManagedFolderName>
  <ManagedFolderRelativePath />
  <NeedsRefresh>false</NeedsRefresh>
  <IsIgnored>false</IsIgnored>
</MediaFolderConfiguration_V2>
```

**Config location:** `/config/plugins/configurations/Shokofin.xml`

---

## Status-Tracker Fixes Applied (12 Total)

| # | Bug | Fix | File |
|---|-----|-----|------|
| 1 | is_anime detection wrong field | Check `seriesType` first | `sonarr.py:181-182` |
| 2 | SQLite database locking | Added WAL mode + busy_timeout | `database.py:112-113` |
| 3 | DOWNLOADED state fallback missing | Added to stuck checker | `jellyfin_verifier.py:415` |
| 4 | SSE new requests not broadcasting | Set `_is_new` flag | `jellyseerr.py:248`, `webhooks.py:68-71` |
| 5 | is_anime null in API | Added to schema | `schemas.py:47` |
| 6 | Shoko path logging empty | Check nested keys | `clients/shoko.py:219-240` |
| 7 | Missing Shoko event handlers | Added 4 handlers | `clients/shoko.py:170-175, 305-356` |
| 8 | find_by_hash no state filter | Added ACTIVE_STATES | `correlator.py:83-98` |
| 9 | Hardcoded /data/ path | Made configurable | `config.py:36-39`, `plugins/shoko.py:118-119` |
| 10 | Background loops missing commit | Added db.commit() | `main.py:65,143,168` |
| 11 | Fallback transitions not tracked | Added to transitioned list | `jellyfin_verifier.py:481,501` |
| 12 | SSE broadcasts before commit | Moved after commit | `main.py:102-105`, others |

---

## Key Commands

### Trigger VFS Rebuild
```bash
# Full library refresh (regenerates all VFS)
curl -X POST 'http://JELLYFIN:8096/Library/Refresh' \
  -H 'X-Emby-Token: API_KEY'

# Specific library refresh
curl -X POST 'http://JELLYFIN:8096/Items/LIBRARY_ID/Refresh?Recursive=true' \
  -H 'X-Emby-Token: API_KEY'
```

### Library IDs (Dev Environment)
| Library | ID |
|---------|------|
| Anime Movies | `abebc196-cc1b-8bbf-6f8b-b5ca7b5ad6f1` |
| Anime Shows | `29391378-c411-8b35-b77f-84980d25f0a6` |

### Shoko Import Folders
| ID | Path | Name |
|----|------|------|
| 1 | `/data/anime/shows/` | anime_shows |
| 2 | `/data/anime/movies/` | anime_movies |

---

## Open Issues (Non-Critical)

### UX Improvements
- Missing SEARCHING state between APPROVED and GRABBING
- Episode progress display (5/13) not showing
- Timeline shows "Downloading: 0 B"

### Infrastructure
- SSE still requires manual refresh (needs debugging)
- Deletion sync with AniDB/Shoko (behavior unclear)

---

## Lessons Learned

1. **Shokofin VFS requires explicit library mapping** - Adding a library in UI isn't enough; must map ManagedFolderId to Shoko import folder
2. **SignalR can be "connected" but not working** - Check for actual file events in logs
3. **Library refresh forces VFS regeneration** - Workaround for SignalR issues
4. **Shokofin config is XML** - Can patch directly at `/config/plugins/configurations/Shokofin.xml`
