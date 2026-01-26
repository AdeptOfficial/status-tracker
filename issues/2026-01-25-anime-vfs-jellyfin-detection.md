# Issue: Anime Matching Complete but Jellyfin Doesn't Detect VFS

**Created:** 2026-01-25
**Status:** Open
**Priority:** High
**Category:** Workflow / Integration

## Problem

After Shoko finishes matching an anime movie:
1. Shoko sends "Movie updated" events (Reason: Added, ImageAdded)
2. Status-tracker receives these events
3. But the request stays stuck at `ANIME_MATCHING` state
4. Jellyfin never detects the file via Shokofin VFS

## Expected Flow

```
ANIME_MATCHING
  → Shoko matches file
  → Shoko generates VFS entry
  → Trigger Jellyfin library scan
  → Jellyfin detects via Shokofin
  → AVAILABLE
```

## Current Behavior

- Shoko SignalR events received (MovieUpdated with ShokoSeriesIDs)
- But no transition to AVAILABLE
- Jellyfin ID remains null

## Possible Causes

1. **VFS not regenerating** - Shokofin VFS might not be auto-regenerating
2. **Library scan not triggered** - Status-tracker might not be triggering Jellyfin scan
3. **Scan timing** - Jellyfin scan happens before VFS is ready
4. **Wrong library** - Jellyfin scanning wrong library (not the Shokofin VFS library)

## Investigation Needed

1. Check if Shokofin VFS shows the new file
2. Check if Jellyfin library scan is being triggered
3. Check Jellyfin verifier logic for anime

## Potential Solution: Add Intermediate State

Consider adding a `VFS_READY` or `MATCHED` state:

```
ANIME_MATCHING → MATCHED (Shoko done) → trigger scan → AVAILABLE
```

This would:
1. Confirm Shoko finished matching
2. Give time for VFS to regenerate
3. Then trigger Jellyfin scan
4. Wait for Jellyfin to detect

## Files to Investigate

- `app/clients/shoko.py` - SignalR event handling
- `app/plugins/shoko.py` - How matching events are processed
- `app/services/jellyfin_verifier.py` - How anime availability is checked
- `app/clients/jellyfin.py` - Library scan trigger

## Related

- Shoko SignalR shows successful matching (ShokoSeriesIDs: [29])
- The Garden of Words test case stuck at anime_matching
