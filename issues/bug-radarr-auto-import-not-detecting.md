# Bug: Radarr Not Auto-Detecting Completed Downloads

**Priority:** Medium
**Status:** Open
**Created:** 2026-01-21
**Category:** Bug / Infrastructure

## Problem

Radarr is not automatically detecting when qBittorrent completes a download. Manual import is required via Radarr UI.

## Symptoms

1. qBittorrent shows torrent at 100% complete with `stalledUP` state
2. File is in correct location: `/data/downloads/complete/`
3. Category is correct: `radarr`
4. Radarr logs show no import activity
5. No `TrackedDownload` or `CompletedDownloadService` logs
6. Manual import from Radarr UI works fine

## Likely Causes

### 1. LXC Memory Pressure (Primary Suspect)
- LXC 220 swap usage at 99.85%
- Services may be thrashing and missing events
- See: `issues/improvements/lxc-220-increase-swap-memory.md`

### 2. Download Client Configuration
- Completed Download Handling may be disabled
- Category mismatch between Radarr config and qBittorrent
- Download client check interval too long

### 3. qBittorrent → Radarr Communication
- qBittorrent not notifying Radarr of completion
- API connectivity verified OK (version check passes)

## Debug Evidence

```bash
# qBittorrent API responds
curl http://gluetun:8080/api/v2/app/version → v5.1.4

# Torrent is complete
"progress": 1
"state": "stalledUP"
"category": "radarr"

# No Radarr import logs
grep -i "TrackedDownload" radarr.log → (empty)
grep -i "CompletedDownloadService" radarr.log → (empty)
```

## Verification Steps

1. Check Radarr → Settings → Download Clients → qBittorrent (VPN)
2. Verify "Completed Download Handling" is enabled
3. Verify "Category" matches qBittorrent category
4. Check "Recent Priority" and polling interval

## Workaround

Manual import via Radarr UI: Activity → Queue → Manual Import

## Related

- LXC 220 swap memory issue
- May affect Sonarr similarly
