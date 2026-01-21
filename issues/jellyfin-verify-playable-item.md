# Bug: Jellyfin Verification Returns Metadata-Only Items

**Date:** 2026-01-21
**Severity:** High
**Component:** Jellyfin Verifier / Fallback Checker

## Problem

`find_item_by_tmdb()` returns Jellyfin items that match the TMDB ID but may not be actual playable media. This causes false-positive "Ready to Watch" status.

## Observed Behavior

1. User requests Suzume (TMDB 916224)
2. Radarr imports, Shoko detects
3. Fallback checker queries Jellyfin: `AnyProviderIdEquals=Tmdb.916224`
4. Jellyfin returns an item (ID: `54417b70f17f37812f64d6fcc0e3e74e`)
5. Status-tracker marks request as AVAILABLE
6. **BUT:** Jellyfin UI shows only 4 movies - Suzume not visible/playable

## Root Cause

The Jellyfin item found is likely a **metadata stub** created by Jellyseerr's sync, not an actual playable movie from Shokofin/library scan.

Jellyfin can have items with TMDB IDs that are:
- Metadata-only (from external sync like Jellyseerr)
- Pending library scan
- Missing media sources

## Proposed Fix

Modify `find_item_by_tmdb()` to verify the item is playable:

```python
async def find_item_by_tmdb(self, tmdb_id: int, media_type: str = "Movie") -> Optional[dict]:
    # ... existing query ...

    if items:
        item = items[0]
        # Verify item has actual media (not just metadata)
        if item.get("MediaSources") or item.get("Path"):
            return item
        else:
            logger.debug(
                f"Found Jellyfin item {item.get('Id')} for TMDB {tmdb_id} "
                f"but it has no MediaSources - likely metadata-only"
            )
            return None
    return None
```

**Alternative:** Add `HasMediaSources=true` to the query if Jellyfin API supports it.

## Additional Context

- Shokofin watches `/data/anime/shows/` but may not watch `/data/anime/movies/`
- Anime Movies library might be a regular Jellyfin library needing manual scan
- The movie file exists at `/data/anime/movies/Suzume (2022)/`

## Workaround

Trigger Jellyfin library scan after Radarr import (we do this in `handle_shoko_movie_available()` but timing may be off).
