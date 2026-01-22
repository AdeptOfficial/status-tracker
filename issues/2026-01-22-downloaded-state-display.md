# State Bug: "downloaded" Shown as Separate Timeline Entry

**Date:** 2026-01-22
**Status:** Open
**Priority:** Low (cosmetic)
**Found During:** "Your Name." anime movie test

---

## Issue

The timeline displays "downloaded" as a separate visible state between "Downloading" and "Matching":

```
Approved      → 08:55 AM
grabbing      → 08:56 AM
Downloading   → 08:56 AM
downloaded    → 08:57 AM  ← Should this be visible?
Matching      → 08:58 AM
```

## Expected Behavior

The `downloaded` state may be an internal transition that shouldn't be displayed to users. Consider:
1. Hiding `downloaded` from timeline (internal state only)
2. Merging with "Downloading" as completion indicator
3. Or renaming to "Import pending" if it's meaningful

## Current Flow

```
DOWNLOADING → DOWNLOADED → IMPORTING/ANIME_MATCHING → AVAILABLE
```

## Questions

- Is `downloaded` a necessary user-facing state?
- Should it show "Download complete" instead of a separate entry?
- Does it provide value or just clutter the timeline?

## Files

- Timeline component: `app/templates/` or frontend
- State definitions: `app/core/state_machine.py`

---

## Notes

The workflow itself works correctly - this is purely a UX/display issue.
