# Feature: Library Sync Should Populate Missing IDs

**Created:** 2026-01-22
**Status:** Open
**Priority:** Medium
**Component:** Services / Library Sync

## Problem

The "Sync Library" button currently only creates new requests from Jellyfin library items. It doesn't update existing requests that may be missing critical ID fields (`jellyfin_id`, `tvdb_id`, `tmdb_id`).

## Use Case

If a request reaches AVAILABLE state but is missing fields due to:
- Race conditions between webhook handlers
- Bugs in webhook handlers (now fixed)
- Manual database issues
- Historical data from before fixes

The user should be able to click "Sync Library" to fill in any missing IDs.

## Current Behavior

Library sync:
1. Fetches all items from Jellyfin
2. Checks if request exists by provider IDs
3. If not exists → creates new request
4. If exists → skips (no update)

## Expected Behavior

Library sync should also:
1. For existing requests missing `jellyfin_id`:
   - Look up Jellyfin item by TVDB/TMDB
   - Set `jellyfin_id` if found
2. For existing requests missing `tvdb_id` or `tmdb_id`:
   - Fetch from Jellyfin item's provider IDs
   - Update if missing

## Implementation Notes

- This serves as a "repair" mechanism for any missed data
- Should log which requests were updated
- Should not overwrite existing non-null values
- Consider showing a summary: "Updated 3 requests with missing IDs"

## Related

- `app/services/library_sync.py`
- Fixed: Jellyseerr/Jellyfin handlers now set IDs (but this is a fallback)
