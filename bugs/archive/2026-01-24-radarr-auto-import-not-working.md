# Radarr Auto-Import Not Working

**Created:** 2026-01-24
**Status:** Open
**Severity:** Medium
**Component:** Radarr / qBittorrent (LXC <media-dev>)

## Issue

Radarr does not automatically import completed downloads from qBittorrent. Manual import is required after each download completes.

## Impact

- Breaks automated pipeline (Jellyseerr → Radarr → qBittorrent → **manual step** → library)
- Status-tracker stuck at "downloaded" state until manual intervention
- User must manually trigger import in Radarr UI

## Current Configuration

**Radarr Download Client Settings:**
- Host: `gluetun` (qBittorrent behind VPN)
- Port: `8080`
- Category: `radarr`
- Remove Completed: Enabled
- Remove Failed: Enabled

**qBittorrent Settings:**
- Default Torrent Management Mode: `Manual`
- Default Save Path: `/data/downloads/complete`
- "Use Category paths in Manual Mode": **Unchecked**
- Auth bypass for `172.20.0.0/16` subnet

## Suspected Causes

### 1. Category Path Not Used
qBittorrent has "Use Category paths in Manual Mode" unchecked. Files download to `/data/downloads/complete/` instead of `/data/downloads/complete/radarr/`. Radarr might expect category subfolder.

### 2. Path Mapping
Radarr and qBittorrent might see different paths for the same files if container mounts differ.

### 3. Torrent State Detection
Radarr polls qBittorrent API to detect completed torrents. If torrent state isn't reported correctly, import won't trigger.

### 4. Category Not Applied
qBittorrent might not be applying the "radarr" category to downloads initiated by Radarr.

## Troubleshooting Steps

1. Check Radarr Activity → Queue for any errors/warnings
2. Check Radarr System → Events for import failures
3. Verify torrent has "radarr" category in qBittorrent UI
4. Enable "Use Category paths in Manual Mode" in qBittorrent and configure category save path
5. Check Radarr logs during download completion

## Test Case

- Request: Akira (1988) via Jellyseerr
- Download completed successfully to `/data/downloads/complete/`
- Radarr did not auto-import
- Manual import required via Radarr UI → Wanted → Manual Import

## Related

- Media stack compose: `configs/dev/stacks/media/docker-compose.yml`
- Similar issue may affect Sonarr (needs verification)


## Earlier duplicate report (merged 2026-10-20 from `bug-radarr-auto-import-not-detecting.md`)

## Bug: Radarr Not Auto-Detecting Completed Downloads

**Priority:** Medium
**Status:** Open
**Created:** 2026-01-21
**Category:** Bug / Infrastructure

### Problem

Radarr is not automatically detecting when qBittorrent completes a download. Manual import is required via Radarr UI.

### Symptoms

1. qBittorrent shows torrent at 100% complete with `stalledUP` state
2. File is in correct location: `/data/downloads/complete/`
3. Category is correct: `radarr`
4. Radarr logs show no import activity
5. No `TrackedDownload` or `CompletedDownloadService` logs
6. Manual import from Radarr UI works fine

### Likely Causes

#### 1. LXC Memory Pressure (Primary Suspect)
- LXC <media-dev> swap usage at 99.85%
- Services may be thrashing and missing events
- See: `issues/improvements/lxc-220-increase-swap-memory.md`

#### 2. Download Client Configuration
- Completed Download Handling may be disabled
- Category mismatch between Radarr config and qBittorrent
- Download client check interval too long

#### 3. qBittorrent → Radarr Communication
- qBittorrent not notifying Radarr of completion
- API connectivity verified OK (version check passes)

### Debug Evidence

```bash
## qBittorrent API responds
curl http://gluetun:8080/api/v2/app/version → v5.1.4

## Torrent is complete
"progress": 1
"state": "stalledUP"
"category": "radarr"

## No Radarr import logs
grep -i "TrackedDownload" radarr.log → (empty)
grep -i "CompletedDownloadService" radarr.log → (empty)
```

### Verification Steps

1. Check Radarr → Settings → Download Clients → qBittorrent (VPN)
2. Verify "Completed Download Handling" is enabled
3. Verify "Category" matches qBittorrent category
4. Check "Recent Priority" and polling interval

### Workaround

Manual import via Radarr UI: Activity → Queue → Manual Import

### Related

- LXC <media-dev> swap memory issue
- May affect Sonarr similarly

## Triage 2026-10-20

**Verdict:** Resolved by later work. **Status:** Resolved (triage, repo evidence; no live check in this pass).
Oct 20: Spider-Man request 24 "proved automatic selection and new-folder import/permissions through all-service Available"; `docs/MEDIA-PERMISSIONS.md` covers the permission cause.
