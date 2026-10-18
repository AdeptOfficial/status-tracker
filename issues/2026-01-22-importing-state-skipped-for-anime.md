# Bug: IMPORTING State Skipped for Anime

**Priority:** Medium
**Status:** Timeline visibility fixed on DEV; original transition proposal superseded
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

## October 17 review and resolution

Current Radarr/Sonarr import handlers intentionally route anime to matching after
receiving import-complete notifications. Existing movie/TV flow tests depend on
that routing. Forcing an unobserved in-progress import state here would obscure
what is actually pending (Shoko/Jellyfin), not measure import duration.

Timeline now labels Radarr/Sonarr `Import` events **Imported**, independent of
current lifecycle state. Radarr anime details explicitly say imported and waiting
for Shoko. Current status remains Matching until verification; no transition,
listener, timeout or episode-state logic changed. Existing history renders the
new label without rewriting data. This addresses the missing import visibility;
a true live import-progress stage would require a reliable start/progress signal.

137 regressions pass, including actual anime movie/TV handlers and labels for
available/downloading/matching states. Existing warnings remain. No new download
was triggered; current end-to-end media pipeline validation remains outstanding.
