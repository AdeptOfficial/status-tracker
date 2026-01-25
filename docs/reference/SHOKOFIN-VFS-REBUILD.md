# Shokofin VFS Rebuild Commands

**Date:** 2026-01-22
**Purpose:** Manual workaround when Shokofin SignalR isn't receiving file events from Shoko

---

## Problem

Shokofin VFS (Virtual File System) doesn't regenerate automatically when:
- SignalR connection to Shoko is broken or not receiving events
- Files are added to media folders but Shokofin doesn't detect them

**Symptom:** Anime content stuck at `anime_matching` state, Jellyfin can't find the content.

---

## Solution: Trigger Library Refresh via API

A Jellyfin library refresh forces Shokofin to regenerate the VFS.

### Full Library Refresh (All Libraries)

```bash
curl -s -X POST 'http://JELLYFIN_HOST:8096/Library/Refresh' \
  -H 'X-Emby-Token: YOUR_API_KEY'
```

### Single Library Refresh

```bash
# Anime Movies library
curl -s -X POST 'http://JELLYFIN_HOST:8096/Items/LIBRARY_ID/Refresh?Recursive=true&MetadataRefreshMode=Default&ImageRefreshMode=Default' \
  -H 'X-Emby-Token: YOUR_API_KEY'
```

---

## Library IDs (Dev Environment)

| Library | ID |
|---------|------|
| Anime Movies | `abebc196cc1b8bbf6f8bb5ca7b5ad6f1` |
| Anime Shows | `29391378c4118b35b77f84980d25f0a6` |
| TV-Shows | `3e840160b2d8a553d88213a62925f0fa` |
| Movies | `f137a2dd21bbc1b99aa5c0f6bf02a805` |

### Get Library IDs

```bash
curl -s -H 'X-Emby-Token: YOUR_API_KEY' \
  'http://JELLYFIN_HOST:8096/Library/VirtualFolders' | jq '.[] | {Name, ItemId}'
```

---

## Integration with Status-Tracker

**Option 1: Add to fallback checker**
When `ANIME_MATCHING` requests are stuck, trigger a library refresh before scanning.

**Option 2: Scheduled task**
Run VFS refresh periodically (e.g., every 10 minutes) as a workaround.

**Option 3: Fix SignalR**
The proper fix is ensuring Shokofin SignalR receives events from Shoko.

---

## Root Cause

Shokofin's SignalR connection can fail silently:
1. Initial connection fails at startup
2. Reconnection may succeed but events aren't delivered
3. File events from Shoko don't trigger VFS regeneration

**Verification:** Check Jellyfin logs for:
```
Shokofin.SignalR.SignalRConnectionManager: Connected to Shoko Server.
```

If no file events logged after file processing, SignalR is broken.

---

## Successful Test: Akira (2026-01-22) - Anime Movie

1. Akira stuck at `anime_matching` for 15+ minutes
2. Shoko matched the file (SignalR events in status-tracker logs)
3. Shokofin SignalR NOT receiving events (VFS empty)
4. Triggered: `POST /Library/Refresh`
5. Shokofin log: `Created 1 entries in VFS folder`
6. Jellyfin found Akira
7. Status-tracker fallback transitioned to `available`

## Successful Test: SNAFU (2026-01-22) - Anime TV

1. SNAFU stuck at `anime_matching` - VFS not generating
2. Root cause: Anime Shows library not configured in Shokofin
3. Fix: Patched `Shokofin.xml` to add MediaFolderConfiguration_V2:
   ```xml
   <MediaFolderConfiguration_V2>
     <LibraryId>29391378-c411-8b35-b77f-84980d25f0a6</LibraryId>
     <Path>/data/anime/shows</Path>
     <ManagedFolderId>1</ManagedFolderId>
     <ManagedFolderName>anime_shows</ManagedFolderName>
     ...
   </MediaFolderConfiguration_V2>
   ```
4. Restarted Jellyfin, triggered refresh
5. VFS generated 13 entries (S1: 1 episode, S2: 12 episodes)
6. Status-tracker transitioned to `available`

## Successful Test: Cosmic Princess Kaguya (2026-01-25) - Anime Movie

1. Movie stuck at `anime_matching` - VFS showed only 3 of 4 movies
2. Root cause: `<FilterMovieLibraries>true</FilterMovieLibraries>`
3. This setting excludes movies without TMDB cross-references in Shoko
4. Movie had no TMDB link: `TMDB={'Movie': [], 'Show': []}`
5. Fix: Set `<FilterMovieLibraries>false</FilterMovieLibraries>`
6. Alternative: Add AniDB ID to `<VFS_AlwaysIncludedAnidbIdList>`
7. Restarted Jellyfin, VFS generated 4 entries
8. Status-tracker transitioned to `available`

---

## Config File Location

```
/config/plugins/configurations/Shokofin.xml
```

Key sections:
- `<LibraryFolders>` - Media folder mappings
- `ManagedFolderId` - Must match Shoko import folder ID (1=anime_shows, 2=anime_movies)
- `<FilterMovieLibraries>` - If true, excludes movies without TMDB (set to false for anime)
- `<VFS_AlwaysIncludedAnidbIdList>` - Whitelist AniDB IDs to always include in VFS

---

## Troubleshooting Checklist

When anime is stuck at `anime_matching`:

1. **Check Shoko** - Is the file matched? (`/api/v3/Series/{id}/File`)
2. **Check SignalR** - Is Shokofin connected? (Jellyfin logs)
3. **Check VFS logs** - How many entries created? (`Created X, skipped Y, Total=Z`)
4. **Check TMDB** - Does series have TMDB link? (`/api/v3/Series/{id}` → IDs.TMDB)
5. **Check FilterMovieLibraries** - Is it filtering out movies without TMDB?
6. **Check library config** - Is the library configured in Shokofin?
