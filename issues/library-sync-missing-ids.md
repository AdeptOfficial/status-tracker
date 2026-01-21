# Status Tracker: Missing Service IDs Causes Incomplete Deletion

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker
**Priority:** High
**Feature:** Deletion Sync / ID Population

## Problem

MediaRequest records can be created without service IDs (radarr_id, jellyfin_id, etc.) in multiple scenarios. This causes deletion sync to skip those services, leaving orphaned files.

### Affected Scenarios

1. **Library Sync** - Items synced from Jellyfin don't have Radarr/Jellyseerr IDs
2. **Re-requests with existing torrents** - Radarr auto-imports without webhooks, no IDs captured
3. **Manual imports** - Files added outside normal flow

### Current Behavior

For library-synced items, deletion shows:
- **Radarr:** "not_needed - No radarr ID found for this item"
- **Jellyseerr:** "not_needed - No jellyseerr ID found for this item"
- **Shoko:** "not_applicable - Shoko not applicable for this media type"

Only Jellyfin deletion works (confirmed) because the `jellyfin_id` is populated during sync.

### Expected Behavior

Library sync should query and populate:
- `radarr_id` - Look up movie in Radarr by TMDB ID
- `jellyseerr_id` - Look up request in Jellyseerr by TMDB ID
- `shoko_series_id` - For anime, look up in Shoko by AniDB/TMDB ID

This would enable full deletion cascade across all services.

## Affected Flow

```
Jellyfin Library Scan
       ↓
  Library Sync (creates MediaRequest)
       ↓
  Missing: radarr_id, jellyseerr_id, shoko_series_id
       ↓
  Deletion → Services skipped with "No ID found"
```

## Screenshots

See deletion log showing "No radarr ID found", "No jellyseerr ID found" for library-synced movies like "Eiga Koe no Katachi" and "Deadpool & Wolverine".

## Technical Notes

### Current Library Sync Logic
- Queries Jellyfin for library items
- Creates MediaRequest with `jellyfin_id` and basic metadata
- Does NOT cross-reference with Radarr/Sonarr/Jellyseerr/Shoko

### Proposed Fix
During library sync, for each item:
1. Query Radarr/Sonarr by TMDB/TVDB ID to get service ID
2. Query Jellyseerr by TMDB ID to get request ID (if exists)
3. For anime: Query Shoko by series name or AniDB ID
4. Populate all IDs in MediaRequest record

### Considerations
- Performance: Additional API calls per item during sync
- Rate limiting: May need to batch or throttle queries
- Optional: Could be a separate "Enrich IDs" background job

## Acceptance Criteria

- [ ] Library-synced movies have `radarr_id` populated
- [ ] Library-synced TV shows have `sonarr_id` populated
- [ ] Library-synced items have `jellyseerr_id` if request exists
- [ ] Library-synced anime have `shoko_series_id` populated
- [ ] Deletion sync shows "confirmed" for all applicable services

## Related Issues

- `radarr-no-webhook-existing-torrent.md` - Cause of missing IDs when torrent exists
- `deletion-missing-qbittorrent.md` - Deletion doesn't remove torrent (would prevent re-request issue)
