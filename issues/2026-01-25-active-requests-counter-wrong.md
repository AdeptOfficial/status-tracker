# Bug: Active Requests Counter Shows 0 When Requests Exist

**Created:** 2026-01-25
**Status:** Open
**Priority:** Medium
**Category:** UI

## Problem

The index page shows "0 requests in progress" even when there are active requests visible on the page.

## Screenshot Evidence

- Shows "0 requests in progress" text
- But "The Garden of Words" card is visible below with "Grabbed" state

## Expected Behavior

Counter should reflect actual number of active (non-terminal) requests.

## Possible Cause

Counter query might be filtering incorrectly, or not counting certain states like "grabbing" or "downloading".

## Files to Investigate

- `app/routers/pages.py` - Index page query
- `app/templates/index.html` - Counter display logic
