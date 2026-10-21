# Issue: Deletion Integration Gaps

**Priority:** Medium
**Status:** Open
**Created:** 2026-01-21
**Category:** Bug / Integration

## Current handoff

Work deferred by the user on2026-10-20. Movie deletion, bulk anime movies, fresh
unattended import/permissions and both season availability checks have the passes
recorded below. Remaining primary blocker is season-safe TV deletion/reconciliation;
TV guard stays enabled. Older pending statements below describe historical tests.
When resumed, read roadmap/2026-10-20-internal-roadmap-legacy.md and the consolidated homeserver session handoff.

## October20 fresh automatic folder/import validation: PASSED

Spider-Man24 was auto-selected and downloaded, imported into a previously absent
folder and reached Available across tracker/Jellyfin/Jellyseerr. Fresh directory
911:911/0755, file0644/nlink2; writer create/rename/delete probe and Jellyfin
read/media probe pass without a permission repair. This closes the one-movie
fresh-folder/unattended acceptance gap for actual DEV roles, not cross-UID group
inheritance or scoped TV removal. User playback remains unverified. See newest DIARY.

## October 20 real anime-movie bulk deletion: PASSED

User selected requests2/4 through authenticated UI. Audits71/72 Complete; both
actual files absent, Radarr records404, Jellyfin items absent, Jellyseerr requests
404/media absent and Shoko file queries0 results. Other request identities and
protected files preserved.21.84GiB reclaimed;27.61GiB free. Success feedback was
invisible after500ms refresh; DEV UI patch now retains accessible result counts
and audit link after reload. Full synthetic Firefox suite covers success, partial,
omitted/empty responses, dismissal and mobile widths. TV scope remains blocked.
See newest diary and homeserver notes/2026-10-20-dev-bulk-delete.json.

## October 20 fresh movie re-request/import: PASSED with manual selection

Interstellar23/Jellyseerr152/Radarr108 reached Available after Knaben/search-helper
repair and normal approved4.21GiB release selection for DEV capacity. Remaining
flow automatic; actual imported hardlink readable in Jellyfin. No manual scan or
status mutation. User playback, unattended selection, fresh-folder creation, TV
scope and anime cleanup remain open. Existing directory was reused. See DIARY.

## October 20 corrected live movie retry: PASSED (issue remains open)

DEV `status-tracker:verified-delete-20261020`;226 regressions and browser suite
pass. Actual process identity confirmed; scoped directory group-write repair and
verified file-first deletion resolved the Interstellar failure. Audit70 Complete:
real file removed, library item absent, provider records cleared, tracker removed,
other requests unchanged. Audit69 remains Incomplete. Added durable retry-directory
migration and strict API absence checks. See newest DIARY and
[operator permission guide](../docs/MEDIA-PERMISSIONS.md).

Fresh re-request/import, fresh-folder creation modes, TV deletion scope and anime
cleanup remain release blockers. No production change. No new download submitted.

## October 20 original live movie test: FAILED (historical evidence)

Authorized DEV Interstellar deletion falsely reported Complete. Radarr removed
its movie record despite file permission failure; tracker/Jellyseerr records were
then removed, but the 4.21GiB file and Jellyfin library item remained. Corrected
audit69 to Incomplete and restored tracker19 as Failed. Do not retry with stale
service IDs until file verification and reconciliation are implemented. See newest
DIARY entry for exact evidence, permissions and private backup location.

Also reproduced: Jellyfin `get_item` treats HTTP400 as None; `/Items` listing
confirmed the supposedly missing item. Verification must distinguish an API error
from an actual404. Re-request flow is NOT passed by an empty Jellyseerr record.

## October 20 current status

**Release blocker; partially mitigated on DEV.** See newest DIARY entry.
The whole-show scope bug and early tracker removal were reproduced by code review
and isolated tests. DEV now blocks TV deletion (single/bulk/external paths) rather
than risk sibling seasons. Failed service operations retain tracker records;
keeping files preserves Jellyseerr availability. 199 regressions and browser
acceptance pass. No real media deletion or re-request was performed.

Remaining acceptance: season-only file operations and monitoring; active-download
handling; explicit whole-show confirmation; shared/multi-season request handling;
Jellyseerr season availability reconciliation; retry/restart and external-deletion
reconciliation; synthetic end-to-end proof followed by an authorized DEV test.

API research: [Jellyseerr v2.7.3 media routes](https://github.com/Fallenbagel/jellyseerr/blob/v2.7.3/server/routes/media.ts)
delete the shared media entity; the status route does not provide a general
single-season reset. Verify the installed version and its scan behavior before
choosing an implementation. Do not delete shared media to reset one season.

## Historical problems

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
- `2026-01-21-deletion-remove-qbittorrent-torrent.md`
