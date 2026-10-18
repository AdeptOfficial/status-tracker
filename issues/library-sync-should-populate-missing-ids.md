# Feature: Library Sync Should Populate Missing IDs

**Created:** 2026-01-22
**Status:** Implemented — DEV visual review pending (production on hold)
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

## Original reported behavior

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

## October 17 approved implementation

Repair phase already exists, but excludes Jellyfin-only entries and never fills
TMDB/TVDB IDs. Match by exact Jellyfin ID first, otherwise unique same-media-type
provider IDs; skip ambiguous or conflicting identities. Fill only missing IDs,
year and available poster metadata, then enrich service IDs. Preserve state,
title and existing non-null fields. Do not equate Shoko IDs with AniDB IDs.
Scope includes typed duplicate detection, honest repair error totals, regression
coverage and the existing admin History → Sync Library flow. No schema migration,
production deployment or destructive media operation.

## Validation

134 regression tests pass, including 21 library-sync and two History cases.
Browser coverage exercises the real admin route with isolated mocked services.
History source/user filters, counts and retained tabs are covered. Existing
`Library Sync` rows remain compatible without a data migration. See
[testing instructions](../docs/TESTING.md) for visual review and limitations.
