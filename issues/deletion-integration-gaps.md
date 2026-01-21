# Issue: Deletion Integration Gaps

**Priority:** Medium
**Status:** Open
**Created:** 2026-01-21
**Category:** Bug / Integration

## Problems

### 1. Shoko Not Triggering "Remove Missing Files"

When deleting anime media via status-tracker dashboard, Shoko shows `not_applicable` instead of triggering a "remove missing files" scan.

**Expected:** Shoko should scan for and remove entries for files that no longer exist on disk.

**Actual:** Shoko deletion sync shows "not_applicable - Shoko not applicable for this media type" even for anime content.

**Evidence:**
- Dreaming Girl (2019) - Movie: Shoko shows `not_applicable`
- SNAFU (2013) - TV: Shoko shows `not_applicable`

Both are anime and should trigger Shoko cleanup.

### 2. Jellyseerr Still Shows Media as Available After Deletion

After successful deletion from Radarr/Sonarr and Jellyfin, Jellyseerr may still show the media as "available" in Jellyfin.

**Expected:** Jellyseerr should reflect that media is no longer available and allow re-requesting.

**Actual:** Jellyseerr shows "confirmed - Request deleted successfully" but may still display media as available in its UI.

**Root Cause:** Jellyseerr caches Jellyfin library state and may not immediately reflect deletions. A library sync or cache clear may be needed.

### 3. Jellyfin Shows "not_needed" for Items Without jellyfin_id

For SNAFU deletion, Jellyfin showed:
```
not_needed - No jellyfin ID found for this item
```

This occurred because the item never reached AVAILABLE state (was still downloading when deleted), so no `jellyfin_id` was recorded.

**This is expected behavior** but worth documenting.

## Sync Timeline Evidence

### Dreaming Girl (2019) - Movie
| Service | Status | Note |
|---------|--------|------|
| Radarr | confirmed | Movie deleted successfully |
| Shoko | not_applicable | Should have triggered cleanup |
| Jellyfin | confirmed | Library scan triggered |
| Jellyseerr | confirmed | Request deleted successfully |

### SNAFU (2013) - TV
| Service | Status | Note |
|---------|--------|------|
| Sonarr | confirmed | Series deleted successfully |
| Radarr | not_applicable | Correct (TV show) |
| Shoko | not_applicable | Should have triggered cleanup |
| Jellyfin | not_needed | No jellyfin_id (never reached AVAILABLE) |
| Jellyseerr | confirmed | Request deleted successfully |

## Proposed Fixes

### For Shoko Integration
1. Add Shoko API call to trigger "remove missing files" scan after anime deletion
2. Or: Call Shoko's file removal API directly for known Shoko series/episode IDs

### For Jellyseerr Sync
1. After deletion, trigger Jellyseerr library sync via API
2. Or: Wait for Jellyseerr's periodic sync to catch up
3. Document expected delay in UI

## Files to Investigate

- `app/services/deletion_service.py` - Deletion logic
- `app/clients/shoko.py` - Shoko API integration
- `app/clients/jellyseerr.py` - Jellyseerr API integration

## Related Issues

- `deletion-missing-qbittorrent.md`
- `deletion-remove-qbittorrent-torrent.md`
