# Bug: Matching State Shows Error Color While Working

**Created:** 2026-01-24 (split from a bundled UI-bugs record, moved from homeserver 2026-10-20)
**Status:** Open, unverified against the current build
**Priority:** Medium
**Category:** UI

## Problem

While a request is in `anime_matching` (Shoko matching in progress) the status
indicator shows the red/error color even though the process is working normally.

## Expected Behavior

- In-progress states use the warning/in-progress color
- Green only when complete
- Red only for actual errors

## Investigation Areas

- State-to-color mapping (per-state `--st` variables in `app/static/style.css`)
- Templates that pick the status class

## Related

- `2026-01-25-ui-episode-status-inconsistency.md` (mixed per-episode colors)
- Branch at the time: `feature/per-episode-tracking`

## Triage 2026-10-20

**Verdict:** Still open, unverified on the current build (repo evidence only). Per-state `--st` colour variables exist now; verify an anime_matching card on DEV.
