# Issue: Shoko Path Matching Fails Due to Import Folder Mismatch

**Date:** 2026-01-25
**Priority:** High
**Status:** Partially Fixed (workaround deployed, proper fix needed)

## Problem

Shoko SignalR FileMatched events weren't matching episodes in the database because of path construction issues:

1. **Leading slash:** Shoko's `RelativePath` starts with `/` (e.g., `/Made in Abyss/Season 1/file.mkv`)
2. **Wrong prefix:** `MEDIA_PATH_PREFIX` was `/data` but should match Shoko import folder (`/data/anime/shows`)
3. **Result:** Constructed path `/data//Made in Abyss/...` didn't match episode's `final_path` `/data/anime/shows/Made in Abyss/...`

## Current Workaround

Applied in this session:
- Added `lstrip("/")` to strip leading slash from relative_path (`shoko.py:120`)
- Added `MEDIA_PATH_PREFIX` env var to `docker-compose.yml`
- Set `MEDIA_PATH_PREFIX=/data/anime/shows` in `.env`

**Limitation:** Single env var doesn't support multiple import folders (TV vs movies have different paths).

## Proper Fix Required

Enhance `handle_file_matched()` in `app/plugins/shoko.py` to:

1. **Query Shoko for import folder path** using `managed_folder_id` from the event:
   ```python
   # event.managed_folder_id tells us which import folder
   # Query: GET /api/v3/ImportFolder/{id} to get the actual path
   import_folder = await shoko_client.get_import_folder(event.managed_folder_id)
   full_path = import_folder['Path'].rstrip('/') + '/' + event.relative_path.lstrip('/')
   ```

2. **Cache import folder mappings** to avoid repeated API calls

3. **Fall back to filename matching** more aggressively if path match fails

## Files to Modify

| File | Change |
|------|--------|
| `app/plugins/shoko.py` | Query import folder from Shoko API |
| `app/clients/shoko.py` | Add `get_import_folder(id)` method |
| `app/config.py` | Remove `MEDIA_PATH_PREFIX` once API-based approach works |

## Testing

1. Request anime TV show (uses `/data/anime/shows` import folder)
2. Request anime movie (uses `/data/anime/movies` import folder)
3. Verify both correctly match via Shoko SignalR events
4. Verify fallback path matching still works

## Related

- Shoko import folders configured: ID 1 = `/data/anime/shows/`, ID 2 = `/data/anime/movies/`
- Original workaround commit: (pending)
