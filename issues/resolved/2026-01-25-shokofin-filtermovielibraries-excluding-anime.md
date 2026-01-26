# Issue: Shokofin FilterMovieLibraries Excluding Anime Without TMDB

**Date:** 2026-01-25
**Severity:** High
**Status:** RESOLVED
**Type:** Infrastructure/Config (Shokofin plugin)

---

## Problem

Anime movies stuck at `anime_matching` state indefinitely. Shokofin VFS regeneration only created entries for 3 of 4 movies, consistently skipping newly added content.

## Symptoms

1. Request stuck at `anime_matching` with `shoko_series_id: null`
2. Shokofin VFS logs showed: `skipped 3, Total=3` (should be 4)
3. Fallback checker triggered library scans but movie never appeared in Jellyfin
4. Manually created VFS entries were deleted on next scan

## Root Cause

**Shokofin setting `<FilterMovieLibraries>true</FilterMovieLibraries>`** excludes movies that don't have TMDB cross-references in Shoko.

The "Cosmic Princess Kaguya!" (AniDB 19701) had no TMDB link:
```
Series 32: TMDB={'Movie': [], 'Show': []}
```

Other movies in VFS all had TMDB IDs:
```
Series 28 (5cm/s): TMDB={'Movie': [38142]}
Series 29 (Garden of Words): TMDB={'Movie': [198375]}
Series 10 (Summer Ghost): TMDB={'Movie': [798544]}
```

## Investigation Path

1. Verified Shoko had the series (ID 32) with file (ID 220)
2. Confirmed Shokofin SignalR was enabled and connected
3. Checked VFS generation logs - consistently showed 3 movies
4. Compared TMDB IDs between working and non-working movies
5. Found `FilterMovieLibraries=true` in Shokofin.xml

## Resolution

Edit `/config/plugins/configurations/Shokofin.xml` in Jellyfin container:

```xml
<!-- Before -->
<FilterMovieLibraries>true</FilterMovieLibraries>

<!-- After -->
<FilterMovieLibraries>false</FilterMovieLibraries>
```

Also added AniDB ID to always-include list (optional backup):
```xml
<VFS_AlwaysIncludedAnidbIdList>
  <int>19701</int>
  <int>3651</int>
</VFS_AlwaysIncludedAnidbIdList>
```

Restart Jellyfin after config change.

## Commands Used

```bash
# Edit config
ssh root@10.0.2.10 'pct exec 220 -- docker exec jellyfin sed -i \
  "s|<FilterMovieLibraries>true</FilterMovieLibraries>|<FilterMovieLibraries>false</FilterMovieLibraries>|" \
  /config/plugins/configurations/Shokofin.xml'

# Restart Jellyfin
ssh root@10.0.2.10 'pct exec 220 -- docker restart jellyfin'
```

## Verification

After restart, VFS showed 4 movies:
```
Byousoku 5 Centimeter [Shoko Series=28] [Shoko Episode=611]
Chou Kaguya_hime_ [Shoko Series=32] [Shoko Episode=631]
Kotonoha no Niwa [Shoko Series=29] [Shoko Episode=623]
Summer Ghost [Shoko Series=10] [Shoko Episode=252]
```

Status-tracker fallback checker found the movie and transitioned to `available`.

## Impact

- All anime movies will now be included in VFS regardless of TMDB status
- New anime content won't get stuck at `anime_matching`
- Trade-off: Movies without TMDB won't have TMDB metadata in Jellyfin (but will still be playable)

## Alternative Solutions

1. **Add TMDB links in Shoko** - Manually link movies to TMDB via Shoko UI
2. **Use VFS_AlwaysIncludedAnidbIdList** - Whitelist specific AniDB IDs
3. **Wait for Shoko auto-match** - Some movies get TMDB links after AniDB updates

## Related Files

- Shokofin config: `/config/plugins/configurations/Shokofin.xml` (in Jellyfin container)
- Reference doc: `/docs/reference/SHOKOFIN-VFS-REBUILD.md`
- Previous fix: `/issues/resolved/2026-01-22-shokofin-vfs-not-regenerating.md`
