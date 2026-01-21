# Status Tracker Dashboard - Time Display Incorrect

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker
**Priority:** Low

## Problem

Time display on the status-tracker dashboard is showing incorrect values.

## Investigation Needed

- Check timezone configuration (`TZ` env var)
- Verify timestamp handling in JavaScript vs Python
- Check if it's a display format issue or actual time calculation

## Related

- From `inbox.txt` quick capture
