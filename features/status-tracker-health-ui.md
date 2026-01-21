# Status Tracker: Health Status UI Tab

**Created:** 2026-01-18
**Implemented:** 2026-01-18
**Status:** Implemented
**Component:** apps/status-tracker

## Request

Create a new UI tab/page that displays the `/api/health` endpoint data in a user-friendly format instead of raw JSON.

## Implementation

Added a new "Status" tab to the navbar that displays:

1. **Overall system status** - Green/yellow/red indicator with "All Systems Operational" or "Degraded Performance"
2. **Version card** - Shows current version (v0.1.0)
3. **Database card** - Connection status with visual indicator
4. **Shoko SignalR card** - Real-time connection status (connected/connecting/disabled/error)
5. **Loaded plugins grid** - Shows all active plugins with green indicators
6. **API endpoints table** - Reference for available REST endpoints

## Files Created/Modified

- `app/templates/status.html` - New status page template
- `app/routers/pages.py` - Added `/status` route
- `app/templates/base.html` - Replaced "API" link with "Status" link in navbar

## Access

Navigate to `/status` or click "Status" in the navbar.

## Screenshots

The page shows:
- Cards grid with Version, Database, and Shoko SignalR status
- Plugin list showing all 6 loaded plugins (jellyfin, jellyseerr, qbittorrent, radarr, shoko, sonarr)
- API endpoints reference table
