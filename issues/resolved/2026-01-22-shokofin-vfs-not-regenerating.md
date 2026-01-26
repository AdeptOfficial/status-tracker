# Issue: Shokofin VFS Not Regenerating After Shoko Processing

**Date:** 2026-01-22
**Severity:** High
**Status:** RESOLVED - SignalR was disabled
**Type:** Infrastructure/Config (not status-tracker code)

---

## Problem

Jellyfin library scans complete but find nothing because Shokofin's Virtual File System (VFS) directories are empty or inaccessible.

## Evidence

From Jellyfin logs:
```
DirectoryNotFoundException: /config/Shokofin/VFS/...
"Library folder is inaccessible or empty, skipping"
"Scan Media Library Completed" at 01:56:05
```

## Flow Breakdown

1. ✅ Download completes
2. ✅ Sonarr imports to `/data/anime/shows/`
3. ✅ Shoko detects files, hashes them, matches to AniDB
4. ❌ Shokofin VFS does NOT regenerate
5. ❌ Jellyfin scans VFS but finds nothing
6. ❌ Request stuck at ANIME_MATCHING

## Root Cause

Shokofin VFS regeneration is either:
- Not triggered automatically after Shoko processing
- Triggered but failing silently
- Has a long delay before regeneration

## Investigation Needed

1. Check Shokofin settings for VFS auto-regeneration
2. Check if manual VFS regeneration works
3. Check Shoko → Shokofin webhook/SignalR integration
4. Check Shokofin logs for VFS errors

## Root Cause Found

**SignalR was disabled in Shokofin settings.** Without SignalR, Shokofin doesn't receive events from Shoko when files are matched, so VFS never regenerates.

## Resolution

1. Enable SignalR in Shokofin: Connection tab → Enable SignalR → Connect
2. Ensure both "Anime Shows" and "Anime Movies" libraries are configured in Shokofin's Library Settings

## Note on Library Configuration

Jellyfin requires separate libraries for Shows vs Movies. Shokofin must be configured for EACH library:
- Anime Shows library
- Anime Movies library

Cannot select a parent "Anime" folder that covers both.

## Impact

- All anime content stuck at ANIME_MATCHING
- Manual intervention required for every anime request
- Breaks the automated workflow for anime content
