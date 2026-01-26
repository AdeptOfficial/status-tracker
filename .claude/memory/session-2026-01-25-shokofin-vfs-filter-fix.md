# Session: Shokofin VFS FilterMovieLibraries Fix

**Date:** 2026-01-25
**Duration:** ~3 hours debugging
**Outcome:** RESOLVED

---

## Summary

Anime movie "Cosmic Princess Kaguya!" was stuck at `anime_matching` state. After extensive debugging, discovered Shokofin's `FilterMovieLibraries=true` setting was excluding movies without TMDB cross-references.

## Timeline

1. **SSE Fix Deployed** - Added `--timeout-keep-alive 60` to Uvicorn (separate issue, resolved)

2. **Test Request Made** - User requested "Cosmic Princess Kaguya!" via Jellyseerr

3. **Progress Issue Noted** - Download progress stuck at 0.0% (5% threshold in qbittorrent.py)
   - Noted for later fix, did not modify code during test

4. **Download Completed** - Transitioned through: approved → grabbing → downloading → downloaded → anime_matching

5. **Stuck at anime_matching** - Shoko SignalR events received, but movie not appearing in Jellyfin

6. **VFS Investigation**:
   - VFS folder showed only 3 movies (should be 4)
   - Logs showed: `skipped 3, Total=3` consistently
   - Manually created VFS entries were deleted on scan

7. **TMDB Discovery**:
   - Working movies all had TMDB IDs in Shoko
   - Kaguya had no TMDB: `TMDB={'Movie': [], 'Show': []}`

8. **Config Finding**:
   - Found `<FilterMovieLibraries>true</FilterMovieLibraries>` in Shokofin.xml
   - This setting excludes movies without TMDB from VFS

9. **Fix Applied**:
   - Set `FilterMovieLibraries=false`
   - Restarted Jellyfin
   - VFS regenerated with 4 movies
   - Fallback checker found movie → transitioned to `available`

## Key Learnings

1. **Shokofin FilterMovieLibraries** - Filters VFS based on TMDB availability
2. **VFS_AlwaysIncludedAnidbIdList** - Can whitelist specific AniDB IDs
3. **VFS generation logs** - Show created/skipped/total counts, useful for debugging
4. **TMDB not always available** - New anime may not have TMDB cross-refs in Shoko

## Files Changed

- `/config/plugins/configurations/Shokofin.xml` (on Jellyfin container)
  - `FilterMovieLibraries: true → false`
  - Added AniDB 19701 to `VFS_AlwaysIncludedAnidbIdList`

## Documentation Created

- `/issues/resolved/2026-01-25-shokofin-filtermovielibraries-excluding-anime.md`
- `/issues/2026-01-25-qbittorrent-progress-threshold.md`
- Updated `/docs/reference/SHOKOFIN-VFS-REBUILD.md`

## Pending Issues

1. **qBittorrent 5% threshold** - Progress doesn't update smoothly (UX issue)
2. **TMDB linking** - Consider automating TMDB cross-references in Shoko

## Commands Reference

```bash
# Check VFS content
ssh root@10.0.2.10 'pct exec 220 -- docker exec jellyfin ls -la "/config/Shokofin/VFS/abebc196-cc1b-8bbf-6f8b-b5ca7b5ad6f1/"'

# Check VFS generation logs
ssh root@10.0.2.10 'pct exec 220 -- docker logs jellyfin 2>&1' | grep -i "Created.*entries"

# Check Shoko series TMDB status
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker sh -c "curl -s -H \"apikey: \$SHOKO_API_KEY\" http://shoko:8111/api/v3/Series/32"' | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('IDs',{}).get('TMDB',{}))"

# Edit Shokofin config
ssh root@10.0.2.10 'pct exec 220 -- docker exec jellyfin sed -i "s|<FilterMovieLibraries>true</FilterMovieLibraries>|<FilterMovieLibraries>false</FilterMovieLibraries>|" /config/plugins/configurations/Shokofin.xml'

# Restart Jellyfin
ssh root@10.0.2.10 'pct exec 220 -- docker restart jellyfin'
```
