# Status Tracker: External Deletion Detection

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker
**Priority:** Medium

## Problem

Currently, deletion tracking only works when:
1. Admin deletes via Dashboard UI → `source: dashboard`
2. Sonarr webhook fires → `source: sonarr`
3. Radarr webhook fires → `source: radarr`

But deletions can happen from other sources that we don't actively detect:
- **Jellyfin UI** - User/admin deletes from Jellyfin library
- **Shoko** - Anime management removes entries
- **Manual file deletion** - Someone deletes files directly from disk
- **Disk failure** - Files lost due to hardware issues
- **Cleanup scripts** - Automated maintenance removes files

The `EXTERNAL` source exists in the enum but there's no mechanism to detect and use it.

## Current Sources

| Source | Detection Method | Status |
|--------|------------------|--------|
| DASHBOARD | Direct API call | ✅ Working |
| SONARR | Webhook (SeriesDelete) | ✅ Working |
| RADARR | Webhook (MovieDelete) | ✅ Working |
| JELLYFIN | Webhook (ItemRemoved) | ⚠️ Not implemented |
| SHOKO | SignalR events | ⚠️ Not implemented |
| EXTERNAL | Periodic sync check | ❌ Not implemented |

## Proposed Solutions

### 1. Jellyfin ItemRemoved Webhook

Add handler for Jellyfin's `ItemRemoved` notification:

```python
# In jellyfin plugin
if notification_type == "ItemRemoved":
    # Find request by jellyfin_id
    request = await find_by_jellyfin_id(item_id)
    if request:
        await delete_request(
            db=db,
            request_id=request.id,
            source=DeletionSource.JELLYFIN,
            skip_services=["jellyfin"],  # Already deleted
        )
```

**Jellyfin Webhook Plugin setup:**
- Enable: "Item Removed" notification type
- Payload includes `ItemId` for correlation

### 2. Shoko SignalR Integration

Listen for Shoko file deletion events via SignalR:

```python
# Shoko SignalR events
- FileDeleted
- SeriesUpdated (when episodes removed)
```

### 3. Periodic Sync Check (Fallback)

Background job that periodically verifies tracked items still exist:

```python
# app/services/sync_checker.py
class SyncChecker:
    async def check_orphaned_requests(self):
        """Find requests where media no longer exists."""
        for request in await get_available_requests():
            exists = await self._verify_exists(request)
            if not exists:
                await mark_as_externally_deleted(request)
```

**Check logic:**
1. For movies: Query Radarr by `radarr_id` - does it exist?
2. For TV: Query Sonarr by `sonarr_id` - does it exist?
3. For all: Query Jellyfin by `jellyfin_id` - does it exist?

**If not found in ANY service:**
- Create DeletionLog with `source: EXTERNAL`
- Set `deleted_by_username: "System (external detection)"`
- Remove from requests table

**Schedule:** Run every 6-24 hours (configurable)

### 4. Manual Reconciliation Button

Admin UI button to trigger immediate sync check:

```
┌─────────────────────────────────┐
│ Library Health                  │
├─────────────────────────────────┤
│ Last check: 2 hours ago         │
│                                 │
│ [Check for Missing Media]       │
│                                 │
│ Found: 2 orphaned requests      │
│ - Movie X (deleted externally)  │
│ - TV Show Y (deleted externally)│
└─────────────────────────────────┘
```

## Implementation Priority

1. **Jellyfin ItemRemoved webhook** - Most common external deletion path
2. **Periodic sync check** - Catches everything else
3. **Shoko SignalR** - Nice to have for anime-specific tracking
4. **Manual reconciliation** - Admin tool for immediate verification

## Files to Modify

- `app/plugins/jellyfin.py` - Add ItemRemoved handler
- `app/services/sync_checker.py` - New periodic sync service
- `app/main.py` - Schedule background job
- `app/routers/api.py` - Admin endpoint for manual check
- `app/config.py` - Add `SYNC_CHECK_INTERVAL` setting

## Related

- `DeletionSource.EXTERNAL` already exists in models.py
- `get_username_for_source()` handles EXTERNAL → "System"
