# UX Issue: Anime Matching State Shows "Importing:" Details

**Created:** 2026-01-25
**Status:** Open
**Priority:** Low
**Category:** UX

## Problem

For anime movies, the timeline shows:
- **State label:** Matching
- **Details:** Importing: [filename].mkv

This is technically correct but confusing - user expects "Matching" state to have matching-related details.

## Why This Happens

In `radarr.py`, when `is_anime=True`:
1. Details are set to `f"Importing: {filename}"`
2. State transitions to `ANIME_MATCHING` (not `IMPORTING`)

So the import details carry over to the anime_matching state.

## Current Flow (Anime)

```
Radarr Import webhook
  → details = "Importing: filename.mkv"
  → state = ANIME_MATCHING (because is_anime=True)
```

## Options

### Option A: Change details based on target state
```python
if request.is_anime:
    target_state = RequestState.ANIME_MATCHING
    details = f"Matching: {filename}"  # Different text for anime
else:
    target_state = RequestState.IMPORTING
    details = f"Importing: {filename}"
```

### Option B: Keep as-is (technically correct)
The details describe what happened (Radarr imported the file), not what's happening next (Shoko matching). The state label shows current state.

### Option C: Add separate timeline event for matching
When Shoko starts matching, add a new event with "Matching: ..." details.

## Recommendation

Option A is simplest - just change the details text based on whether it's anime or not.

## Related

- Part of "Importing:" label fix session
- Anime flow: DOWNLOADING → DOWNLOADED → ANIME_MATCHING → AVAILABLE
