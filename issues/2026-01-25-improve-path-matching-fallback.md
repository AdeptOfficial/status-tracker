# Feature: Improve Episode Path Matching with Better Fallbacks

**Date:** 2026-01-25
**Priority:** Medium
**Status:** Enhancement Requested

## Background

During testing, Shoko FileMatched events failed to match episodes due to path mismatches. While the primary fix is querying Shoko's import folder (see `2026-01-25-shoko-path-matching.md`), the fallback matching could be more robust.

## Current Behavior

`find_episode_by_path()` in `app/plugins/shoko.py` tries:
1. **Exact path match** - `Episode.final_path == full_path`
2. **Filename match** - `Episode.final_path.endswith(filename)`
3. **Parent directory match** - If multiple filename matches, filter by parent dir

## Problem

No logging when matching fails, making debugging difficult. Also, the fallback only fires if exact match fails - but it's silently returning `None` without indicating why.

## Proposed Enhancements

### 1. Add Debug Logging

```python
async def find_episode_by_path(db, full_path, relative_path) -> Optional[Episode]:
    # Try exact match
    episode = ...
    if episode:
        logger.debug(f"Found episode by exact path: {full_path}")
        return episode

    logger.debug(f"No exact match for path: {full_path}")

    # Try filename match
    filename = ...
    episodes = ...

    if not episodes:
        logger.debug(f"No episode found with filename: {filename}")
        return None

    if len(episodes) == 1:
        logger.debug(f"Found episode by filename: {filename}")
        return episodes[0]

    logger.debug(f"Multiple matches ({len(episodes)}) for filename: {filename}")
    # ... parent dir filtering
```

### 2. Add Alternative Matching Strategies

```python
# Try matching by episode pattern in filename
# e.g., S01E03 -> season=1, episode=3
import re
match = re.search(r'S(\d+)E(\d+)', filename, re.IGNORECASE)
if match:
    season, ep = int(match.group(1)), int(match.group(2))
    # Query episodes by season/episode number for anime_matching requests
```

### 3. Log Unmatched Events for Analysis

```python
# When no match found, log details for debugging
logger.warning(
    f"Shoko FileMatched event unmatched: "
    f"file_id={event.file_id}, folder_id={event.managed_folder_id}, "
    f"path={event.relative_path}"
)
```

## Files to Modify

| File | Change |
|------|--------|
| `app/plugins/shoko.py` | Add logging, improve fallback logic |

## Testing

1. Temporarily break path matching (wrong MEDIA_PATH_PREFIX)
2. Verify logs show why matching failed
3. Verify filename fallback correctly matches episode
4. Verify S01E03 pattern matching works as fallback
