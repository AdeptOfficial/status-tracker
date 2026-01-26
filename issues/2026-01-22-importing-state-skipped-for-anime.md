# Bug: IMPORTING State Skipped for Anime

**Priority:** Medium
**Status:** Open
**Created:** 2026-01-22
**Category:** Bug / State Machine

## Problem

For anime content, the state machine skips `IMPORTING` and transitions directly from `DOWNLOADED` to `ANIME_MATCHING`. This doesn't match the expected flow in MVP.md.

## Expected Flow (per MVP.md)

```
DOWNLOADED → IMPORTING → ANIME_MATCHING → AVAILABLE
```

## Actual Flow

```
DOWNLOADED → ANIME_MATCHING (IMPORTING skipped)
```

## Evidence

Console logs from "Rascal Does Not Dream of a Dreaming Girl" (2019):
```
state: "downloaded" → state: "anime_matching"
```

Timeline showed:
- downloaded (09:32 AM) via qbittorrent
- Matching (09:33 AM) via radarr - shows "Importing: [Pyon] Rascal..."

The Radarr import webhook IS firing (shows import details in Matching state), but the IMPORTING state is never displayed.

## Root Cause

In `app/core/state_machine.py` line 35:
```python
RequestState.DOWNLOADED: [RequestState.IMPORTING, RequestState.ANIME_MATCHING, RequestState.FAILED],
```

The state machine allows direct transition from DOWNLOADED → ANIME_MATCHING. The Radarr plugin likely transitions directly to ANIME_MATCHING for anime content instead of going through IMPORTING first.

## Impact

- Users don't see the "Importing" phase in the timeline
- Harder to debug if import fails (no visibility into import state)
- Inconsistent with MVP.md documentation

## Fix Required

1. For anime: `DOWNLOADED → IMPORTING → ANIME_MATCHING`
2. Radarr/Sonarr import webhook should transition to IMPORTING
3. Shoko match signal should transition from IMPORTING → ANIME_MATCHING
4. Update state machine if needed

## Related

- MVP.md state machine documentation
- `app/plugins/radarr.py` - import webhook handler
- `app/plugins/sonarr.py` - import webhook handler
