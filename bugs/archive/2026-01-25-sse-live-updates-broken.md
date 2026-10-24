# Bug: SSE Live Updates Not Refreshing (Regression)

**Created:** 2026-01-25
**Status:** Open
**Priority:** High
**Category:** Real-time Updates

## Problem

SSE (Server-Sent Events) live updates are not refreshing the UI automatically. The page shows "Live updates active" but content doesn't update without manual refresh.

## Context

- Was working before recent deployment
- Regression likely caused by recent code changes
- Current deploy includes "Importing:" label fix changes

## Symptoms

- Green "Live updates active" indicator shows
- But UI doesn't update when state changes
- Manual page refresh required to see new state

## Expected Behavior

UI should automatically refresh when:
- State changes (approved → grabbing → downloading, etc.)
- Download progress updates
- New timeline events added

## Possible Causes

1. SSE endpoint not sending events
2. Frontend not handling events correctly
3. Broadcaster not being called on state changes
4. Event listener not triggering htmx refresh

## Files to Investigate

- `app/core/broadcaster.py` - SSE broadcast logic
- `app/routers/sse.py` - SSE endpoint
- `app/templates/detail.html` - Frontend SSE handling (lines 436-528)
- `app/core/state_machine.py` - Check if broadcaster is called on transitions

## Debugging Steps

1. Check browser console for SSE connection errors
2. Check if SSE endpoint is sending events: `curl -N http://<media-dev>:8100/api/sse`
3. Check server logs for broadcast calls

## Earlier report (2026-01-24, merged from homeserver 2026-10-20)

During download testing the UI showed 3% progress while a manual refresh showed 18%.
Investigation areas noted then: SSE connection stability, event emission frequency,
frontend listener handling, buffering or batching.

## Triage 2026-10-20

**Verdict:** Resolved by later work. **Status:** Resolved (triage, repo evidence; no live check in this pass).
Oct 20 roadmap lists live updates and reconnection as verified; detail and home pages pass acceptance with SSE active.
