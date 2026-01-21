# Issue: "Import:" Label Should Say "Importing:"

**Priority:** Low
**Status:** Open
**Created:** 2026-01-21
**Category:** UI/UX

## Problem

In the timeline/detail view, the IMPORTING state shows details as:
```
Import: Rascal Does Not Dream of a Dreaming Girl (2019) (BDRip 1080p HEVC...).mkv
```

It should say:
```
Importing: Rascal Does Not Dream of a Dreaming Girl (2019) (BDRip 1080p HEVC...).mkv
```

## Current Behavior

The state label uses "Import:" as a prefix for the details text.

## Expected Behavior

The state label should use "Importing:" to match the progressive tense of other states (Downloading, Matching, etc.).

## Files to Modify

- `app/templates/detail.html` - Timeline entry text formatting
- Possibly `app/plugins/radarr.py` or `app/plugins/sonarr.py` - If the text is set during state transition

## Screenshot

User reported seeing "Import:" instead of "Importing:" in the UI during the IMPORTING state.
