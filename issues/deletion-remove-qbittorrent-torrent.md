# Bug: Deletion Should Remove Torrent from qBittorrent

**Date:** 2026-01-21
**Severity:** Medium
**Component:** Deletion Orchestrator

## Problem

When deleting media via status-tracker's deletion flow, the torrent remains in qBittorrent. If the same content is re-requested:

1. Jellyseerr sends new request
2. Radarr searches and sends grab to qBittorrent
3. qBittorrent already has the data (same torrent hash) → completes instantly
4. Radarr never sees "downloading" state → doesn't detect completion
5. Import never triggers, request stuck

## Current Deletion Flow

| Service | Action | Status |
|---------|--------|--------|
| status-tracker | Remove request | ✅ |
| Radarr | Delete movie + files | ✅ |
| Jellyfin | Remove from library | ✅ |
| Jellyseerr | Clear request | ✅ |
| **qBittorrent** | **Remove torrent** | ❌ Missing |

## Proposed Fix

Add qBittorrent cleanup step to deletion orchestrator:

1. Look up torrent by `download_id` (stored during grab)
2. Call qBittorrent API to remove torrent **with files**: `POST /api/v2/torrents/delete`
3. **CRITICAL:** Must set `deleteFiles=true` - removing just the torrent entry leaves the file in `/data/downloads/complete/`

## API Reference

```python
# qBittorrent Web API
POST /api/v2/torrents/delete
  hashes: torrent hash (or "all")
  deleteFiles: true  # MUST be true to prevent instant-completion on re-request
```

## Root Cause Analysis

When user manually removed torrent from qBittorrent UI (without deleting files):
1. Torrent entry removed from qBittorrent
2. File remained in `/data/downloads/complete/Suzume.2022.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-Arg0.mkv`
3. On re-request, qBittorrent re-added torrent and found existing file
4. Torrent marked complete instantly (no downloading state)
5. Radarr's download monitor never saw state transition → never triggered import

## Debug Information

**File location after "removing" torrent:**
```
/data/downloads/complete/Suzume.2022.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-Arg0.mkv
Timestamp: Jan 20 19:13 (from previous download session)
Size: 36937550565 bytes (34.4 GB)
```

**qBittorrent behavior:**
- Adding torrent with existing matching file → instant "completed" state
- Radarr polls qBittorrent queue but torrent was never "downloading"
- Radarr's `DownloadMonitoringService` doesn't detect the completion

## Edge Cases to Consider

- Torrent shared by multiple movies (rare but possible)
- Torrent still seeding (respect seed ratio settings?)
- Torrent hash not stored in status-tracker

## Workaround

Restart Radarr after deletion to force re-scan of qBittorrent state on next request.

## Reproduction

1. Request anime movie via Jellyseerr
2. Wait for download + import
3. Delete via status-tracker dashboard
4. Re-request same movie
5. Observe: Radarr doesn't detect completed download
