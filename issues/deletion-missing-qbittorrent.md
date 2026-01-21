# Status Tracker: Deletion Doesn't Remove Torrent from qBittorrent

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker
**Priority:** High
**Feature:** Deletion Sync

## Problem

When deleting a request via status-tracker dashboard, the deletion orchestrator removes the item from Sonarr/Radarr and Jellyseerr, but does NOT remove the active torrent from qBittorrent.

### Current Behavior

Deletion of SPY x FAMILY (mid-download at 25.9%):
- ✓ Sonarr: Series deleted successfully
- ✓ Jellyseerr: Request deleted successfully
- ✗ qBittorrent: Torrent continues downloading

User had to manually open qBittorrent and remove the torrent.

### Expected Behavior

When `delete_files=True`, the deletion orchestrator should:
1. Stop the torrent in qBittorrent
2. Remove the torrent (with data) from qBittorrent
3. Then proceed with Sonarr/Radarr deletion

## Technical Details

The MediaRequest stores `qbit_hash` which can be used to identify and remove the torrent:
- Hash: `7912e46a98f0816b942c00a0c9ceb3189398ba5f`

### qBittorrent API

```
DELETE /api/v2/torrents/delete
Parameters:
  - hashes: torrent hash(es)
  - deleteFiles: true/false
```

### Proposed Fix

In `deletion_orchestrator.py`, add qBittorrent deletion step:

```python
# Before deleting from Sonarr/Radarr
if request.qbit_hash:
    await qbittorrent_client.delete_torrent(
        hash=request.qbit_hash,
        delete_files=delete_files
    )
```

## Acceptance Criteria

- [ ] Active downloads are stopped when request is deleted
- [ ] Torrent is removed from qBittorrent
- [ ] Downloaded files are removed (when delete_files=True)
- [ ] Deletion sync timeline shows qBittorrent status (pending/confirmed)
