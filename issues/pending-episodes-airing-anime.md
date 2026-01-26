# Issue: Pending Episodes Display for Currently Airing Anime

**Created:** 2026-01-26
**Status:** Open
**Priority:** Low (UX consideration)

## Problem

For anime that are still airing (releasing weekly), status-tracker shows future unaired episodes as "pending" with "Searching" status.

Example: "The Invisible Man and His Soon-to-Be Wife"
- Episodes 1-3: Downloading (these have aired)
- Episodes 4-12: Showing as "pending" / "Searching"

## Current Behavior

All episodes in the season are tracked, even those that haven't aired yet. Sonarr marks these as "missing" and searches for them, but they won't be found until they air.

## Questions to Resolve

1. Should unaired episodes be hidden entirely?
2. Should they show a different status like "Unaired" or "Upcoming"?
3. Should we show the air date for upcoming episodes?
4. Is the current behavior acceptable (just needs better labeling)?

## Possible Solutions

### Option A: Hide Unaired Episodes
- Only show episodes that have aired (air date <= today)
- Pro: Cleaner UI, no confusion
- Con: Loses visibility into what's coming

### Option B: "Unaired" Status
- Add new status for episodes with future air dates
- Show air date in the UI
- Pro: Full visibility, clear expectations
- Con: More complexity

### Option C: Collapse Unaired
- Show count of unaired episodes but collapsed
- e.g., "+ 9 episodes (airing weekly)"
- Pro: Clean but informative
- Con: Medium complexity

## Technical Notes

- Air date info available from Sonarr API (`episodes[].airDateUtc`)
- Would need to fetch episode details from Sonarr to get air dates
- Currently only tracking episodes that Sonarr sends via webhook

## User Input Needed

Waiting for user to decide preferred behavior.
