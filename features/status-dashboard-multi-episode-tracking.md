# Status Dashboard: Multi-Episode Tracking

**Created:** 2026-01-18
**Component:** status-tracker (apps/status-tracker/)
**Priority:** Medium
**Status:** Open

## Problem

The status dashboard currently tracks only a single episode's status, even when a TV series request involves multiple episodes or seasons. This creates confusion for users who can't see the full download progress.

**Screenshot shows:**
- SPY x FAMILY request shows "Season 2, Episode 12" in sidebar
- Timeline shows "Found" event only for S02E01
- Progress bar shows 0.0% with no context on what's being tracked
- No visibility into other episodes in the queue

## Expected Behavior

1. **Episode list view** - Show all episodes being downloaded for a series request
2. **Per-episode progress** - Individual progress bars or status indicators for each episode
3. **Aggregate progress** - Overall completion percentage (e.g., "12/25 episodes downloaded")
4. **Clear status labels** - Users should understand what stage each episode is in:
   - Searching
   - Found (with release info)
   - Downloading (with %)
   - Importing
   - Available

## Proposed UI Improvements

```
Current Status: Downloading
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall: 3/25 episodes (12%)

Season 1:
  ├─ E01-E12: ✓ Available
Season 2:
  ├─ E01: ↓ Downloading (45%)
  ├─ E02: ↓ Downloading (12%)
  ├─ E03: 🔍 Searching...
  └─ E04-E12: ⏳ Queued
```

## Technical Considerations

- Sonarr API provides episode-level status via `/api/v3/episode?seriesId=X`
- qBittorrent can report per-torrent progress
- May need to correlate torrent files to episode numbers
- Season packs vs individual episode downloads have different tracking needs

## Deletion Verification for Multi-Episode Content

When deleting a TV series (especially anime), verification needs to account for multiple files:

**Current limitation:**
- Deletion sync deletes at series level (Sonarr series ID, Shoko series ID)
- No verification that individual episode files were actually removed
- No feedback on partial deletions (e.g., some episodes deleted, others failed)

**Needed improvements:**

1. **Pre-deletion inventory**
   - Query Sonarr for episode count before deletion
   - Query Jellyfin for episode items under the series
   - Store expected file count in DeletionLog

2. **Post-deletion verification**
   - Verify all episode files are gone from disk
   - Verify all episodes removed from Jellyfin library
   - Report partial failures (e.g., "Deleted 23/25 episodes, 2 failed")

3. **Shoko-specific considerations**
   - Shoko detects deletions via file system scans, not API calls
   - May need to trigger rescan and wait for completion
   - Verify AniDB entries are unlinked

**Proposed DeletionLog enhancements:**
```python
# Additional fields for multi-file tracking
episode_count: int           # Total episodes in series
episodes_deleted: int        # Successfully deleted
episodes_failed: int         # Failed to delete
partial_deletion: bool       # True if some episodes remain
```

**UI improvements for deletion logs:**
```
Charlotte (2015) - COMPLETE
├─ Episodes: 13/13 deleted
├─ Sonarr: ✓ Series removed
├─ Shoko: ✓ Series unlinked
├─ Jellyfin: ✓ 13 episodes removed
└─ Jellyseerr: ✓ Request cleared
```

## Related

- `ideas/features/request-status-dashboard.md` - Original feature spec
- `apps/status-tracker/` - Current implementation
