# Handoff: qBittorrent Deletion Integration

**Date:** 2026-01-21
**Status:** In Progress (not deployed)

## Context

User wants to fix deletion integration. When deleting media from the dashboard, qBittorrent torrents are NOT being removed - they stay in the client and cause issues on re-request.

## What Was Done

### 1. Added `delete_torrent()` method to qBittorrent client
**File:** `app/clients/qbittorrent.py`

```python
async def delete_torrent(self, hash: str, delete_files: bool = True) -> tuple[bool, str]:
```

This method:
- Authenticates with qBittorrent
- Checks if torrent exists
- Deletes torrent (with or without files)
- Returns (success, message)

### 2. Started updating deletion orchestrator
**File:** `app/services/deletion_orchestrator.py`

- Added import for `QBittorrentClient`
- Added `qbittorrent` to `_determine_services()` method

## What Still Needs To Be Done

### 1. Add `qbit_hash` to DeletionLog model
**File:** `app/models.py`

The `DeletionLog` model is missing `qbit_hash`. Without it, we can't delete from qBittorrent after the request is deleted from DB.

Add after line ~205 (after `jellyseerr_id`):
```python
qbit_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
```

### 2. Update `_create_deletion_log()` in deletion orchestrator
**File:** `app/services/deletion_orchestrator.py`

In the `_create_deletion_log` method (~line 227), add:
```python
qbit_hash=request.qbit_hash,
```

### 3. Update `_sync_external_services()` order
**File:** `app/services/deletion_orchestrator.py`

qBittorrent should be FIRST in the sync order (before Sonarr/Radarr):
```python
ordered_services = []
if "qbittorrent" in services:
    ordered_services.append("qbittorrent")  # FIRST - stop torrent before deleting files
if "sonarr" in services:
    ordered_services.append("sonarr")
# ... rest
```

### 4. Add qBittorrent handling in `_sync_service()`
**File:** `app/services/deletion_orchestrator.py`

Add case for qbittorrent in the sync method:
```python
elif service == "qbittorrent" and deletion_log.qbit_hash:
    async with QBittorrentClient() as qbit:
        success, message = await qbit.delete_torrent(
            deletion_log.qbit_hash, delete_files=delete_files
        )
```

### 5. Create database migration
Add `qbit_hash` column to `deletion_logs` table:
```sql
ALTER TABLE deletion_logs ADD COLUMN qbit_hash VARCHAR(100);
```

### 6. Test and deploy
- User must approve deployment
- Test by deleting media and verifying torrent is removed from qBittorrent

## Files Changed (not deployed)

| File | Status |
|------|--------|
| `app/clients/qbittorrent.py` | Done - added `delete_torrent()` |
| `app/services/deletion_orchestrator.py` | Partial - added import and `_determine_services` |
| `app/models.py` | TODO - add `qbit_hash` to DeletionLog |

## Related Issues

- `issues/deletion-missing-qbittorrent.md`
- `issues/deletion-remove-qbittorrent-torrent.md`
- `issues/deletion-integration-gaps.md`
