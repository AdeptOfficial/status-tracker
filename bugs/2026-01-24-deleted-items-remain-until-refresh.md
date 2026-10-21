# Bug: Deleted Items Still Showing Until Refresh

**Created:** 2026-01-24 (split from a bundled UI-bugs record, moved from homeserver 2026-10-20)
**Status:** Open, unverified against the current build
**Priority:** Medium
**Category:** UI / Real-time Updates

## Problem

After deleting a request, it may still appear in the list until a manual page refresh.

## Expected Behavior

Deleted items disappear immediately through an SSE update.

## Investigation Areas

- Deletion event emission
- Frontend state handling after delete events
- Possible race with a concurrent refresh

## Related

- Branch at the time: `feature/per-episode-tracking`
- `2026-01-25-sse-live-updates-broken.md`

## Triage 2026-10-20

**Verdict:** Still open, unverified on the current build (repo evidence only). UI rebuilt since; verify a delete on DEV without refreshing.
