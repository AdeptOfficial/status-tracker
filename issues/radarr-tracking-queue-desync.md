# Status Tracker: Radarr Tracking Queue Desync

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker / Radarr Integration
**Priority:** Medium
**Feature:** State Machine / Download Tracking

## Problem

Radarr successfully sends a torrent to qBittorrent but fails to add it to its internal tracking queue. This causes completed downloads to be ignored - Radarr's "Completed Download Handling" never processes them because they aren't tracked.

### Observed Behavior

1. Radarr searches for release
2. Radarr sends release to qBittorrent → **Success**
3. Radarr tries to add to internal queue → **Fails**
4. qBittorrent downloads and completes torrent
5. Radarr's completed download handler never sees it (not in queue)
6. No import webhook sent to status-tracker
7. Request stuck at `download_done`

### Logs

```
[Info] DownloadService: Report for Rascal Does Not Dream of a Sister Venturing Out (2023) sent to qBittorrent (VPN)
[Warn] ProcessDownloadDecisions: Couldn't add release '[Arid] Rascal Does Not Dream of a Sister Venturing Out (2023)...' from Indexer Nyaa.si (Prowlarr) to download queue.
```

File exists in qBittorrent at 100%, seeding, but Radarr shows "Wanted".

## Technical Context

### Root Cause

Unknown - Radarr internal queue management issue. Possible causes:
- Race condition in queue handling
- Database lock during add
- Duplicate detection false positive

### Queue vs Download Client

Radarr maintains two separate states:
1. **Download client** (qBittorrent) - has torrent, downloading/seeding
2. **Internal queue** - tracked downloads to process

Completed download handling only processes items in the internal queue.

### Workaround

Manual Import:
1. Radarr → Activity → Queue → Manual Import
2. Select `/data/downloads/complete/`
3. Import completed file

## Reproduction

Not consistently reproducible. Observed when:
- Torrent previously existed in qBittorrent (from old request)
- Radarr re-grabs same release
- May be related to duplicate detection

## Impact

- Status-tracker never reaches `importing` state
- No webhook sent
- User must manually import

## Acceptance Criteria

- [ ] Understand why queue add fails when download client succeeds
- [ ] Detect and handle queue desync
- [ ] Option 1: Status-tracker polls qBittorrent for untracked completed downloads
- [ ] Option 2: Radarr configuration fix to prevent desync

## Related Issues

- `radarr-no-webhook-existing-torrent.md` - Different but related (Radarr can't add duplicate torrents)
- This issue: Radarr CAN add to qBit but FAILS to track internally
