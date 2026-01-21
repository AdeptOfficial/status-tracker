# Status Tracker: No Radarr Webhook When Torrent Already Exists

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker
**Priority:** Medium
**Feature:** State Machine / Radarr Integration

## Problem

When a movie is re-requested and the torrent file already exists in qBittorrent (from a previous download), Radarr auto-imports the file without sending any webhooks. This leaves the status-tracker request stuck at `approved` state.

### Reproduction Steps

1. Request an anime movie via Jellyseerr
2. Movie downloads and imports successfully
3. Delete the request from status-tracker (with files)
4. Torrent remains in qBittorrent (seeding)
5. Re-request the same movie
6. Jellyseerr sends AUTO_APPROVED webhook → status-tracker creates request
7. Radarr detects existing torrent, auto-imports
8. **No Grab webhook** (didn't search/grab)
9. **No Download webhook** (considers it already imported)
10. Status-tracker stuck at `approved`

### Current Behavior

- Request created at `approved` state
- Radarr shows movie as "Downloaded (Monitored)" - green
- No webhooks received by status-tracker
- Request never progresses past `approved`

### Expected Behavior

Status-tracker should reach `available` state when the movie is already in Radarr/Jellyfin.

## Technical Context

### Why Radarr Doesn't Send Webhooks

- **Grab** webhook: Only sent when Radarr actively grabs a release
- **Download** webhook: Only sent when Radarr imports a NEW file

When Radarr auto-imports an existing file, neither condition triggers.

### Potential Solutions

#### Option 1: Polling-based Detection
Add a background task that polls Radarr for movies matching tracked requests and updates state accordingly.

```python
# Pseudo-code
async def check_radarr_status():
    for request in requests_at_approved_state:
        if request.tmdb_id:
            radarr_movie = await radarr_client.get_by_tmdb(request.tmdb_id)
            if radarr_movie and radarr_movie.has_file:
                transition(request, AVAILABLE)
```

#### Option 2: Jellyseerr AVAILABLE Webhook
Rely on Jellyseerr sending MEDIA_AVAILABLE when it detects the movie in Jellyfin. This already works but may have delay.

#### Option 3: Timeout + Fallback Check
After a timeout at `approved` state, check if media exists in Radarr/Jellyfin.

## Workaround

1. Delete the torrent from qBittorrent before re-requesting
2. Or manually trigger state update via API

## Acceptance Criteria

- [ ] Re-requested movies with existing torrents reach `available` state
- [ ] No manual intervention required
- [ ] Solution handles edge case gracefully

## Related Issues

- `deletion-missing-qbittorrent.md` - If deletion removed torrent, this wouldn't happen
