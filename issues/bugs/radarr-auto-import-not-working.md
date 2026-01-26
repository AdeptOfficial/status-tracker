# Radarr Auto-Import Not Working

**Created:** 2026-01-24
**Status:** Open
**Severity:** Medium
**Component:** Radarr / qBittorrent (LXC 220)

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
