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


## Earlier duplicate report (merged 2026-10-20 from `deletion-missing-qbittorrent.md`)

## Status Tracker: Deletion Doesn't Remove Torrent from qBittorrent

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker
**Priority:** High
**Feature:** Deletion Sync

### Problem

When deleting a request via status-tracker dashboard, the deletion orchestrator removes the item from Sonarr/Radarr and Jellyseerr, but does NOT remove the active torrent from qBittorrent.

#### Current Behavior

Deletion of SPY x FAMILY (mid-download at 25.9%):
- ✓ Sonarr: Series deleted successfully
- ✓ Jellyseerr: Request deleted successfully
- ✗ qBittorrent: Torrent continues downloading

User had to manually open qBittorrent and remove the torrent.

#### Expected Behavior

When `delete_files=True`, the deletion orchestrator should:
1. Stop the torrent in qBittorrent
2. Remove the torrent (with data) from qBittorrent
3. Then proceed with Sonarr/Radarr deletion

### Technical Details

The MediaRequest stores `qbit_hash` which can be used to identify and remove the torrent:
- Hash: `7912e46a98f0816b942c00a0c9ceb3189398ba5f`

#### qBittorrent API

```
DELETE /api/v2/torrents/delete
Parameters:
  - hashes: torrent hash(es)
  - deleteFiles: true/false
```

#### Proposed Fix

In `deletion_orchestrator.py`, add qBittorrent deletion step:

```python
## Before deleting from Sonarr/Radarr
if request.qbit_hash:
    await qbittorrent_client.delete_torrent(
        hash=request.qbit_hash,
        delete_files=delete_files
    )
```

### Acceptance Criteria

- [ ] Active downloads are stopped when request is deleted
- [ ] Torrent is removed from qBittorrent
- [ ] Downloaded files are removed (when delete_files=True)
- [ ] Deletion sync timeline shows qBittorrent status (pending/confirmed)

## Triage 2026-10-20

**Verdict:** Resolved by later work. **Status:** Resolved (triage, repo evidence; no live check in this pass).
`app/clients/qbittorrent.py` has `delete_torrent` calling `/api/v2/torrents/delete`; Oct 20 verified movie deletion checked file, library and provider absence. TV deletion remains blocked by a separate guard (see `issues/2026-01-21-deletion-integration-gaps.md`).

## Reopened 2026-10-23

**Status:** Open (reopened). The 2026-10-20 triage resolved this from repo evidence only: the client has
`delete_torrent` (`app/clients/qbittorrent.py`), but **nothing calls it**. `grep -rn delete_torrent app`
finds only the definition; `deletion_orchestrator.py` and `deletion_verifier.py` never mention
qBittorrent.

Live evidence (DEV, 2026-10-23): qBittorrent held **12 torrents in `missingFiles`**, category
`tv-sonarr`, all for media deleted in earlier DEV deletion tests (Witch Hat Atelier episodes and packs,
Cyberpunk: Edgerunners S2). Their files were gone, the torrents stayed. They were removed by hand
(`deleteFiles=false`). Consequences match the original problem: stale torrents keep hashes that a
re-request can collide with, and they clutter the client.

Next: call `delete_torrent` from the deletion orchestrator for every hash recorded on the request and
its episodes (with `deleteFiles` matching the deletion), record the result in the deletion sync events,
and add a test; the acceptance criteria above still apply.
