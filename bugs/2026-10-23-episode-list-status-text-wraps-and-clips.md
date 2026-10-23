# Episode list: status text wraps and is clipped on the request card

**Created:** 2026-10-23
**Status:** Open (needs fixing; no solution proposed yet)
**Severity:** Low (display only)
**Found:** DEV regular-TV test (Gotham S5, 12 episodes), request card with *Show episodes* expanded,
reported by the owner with a screenshot
**Related:** [per-episode progress and request state](../features/2026-01-18-per-episode-progress-and-request-state.md)

## Problem

In the expanded episode list on the request card:

- The per-episode status text (`⬇ progress unknown`) wraps onto two lines, and on at least one row it
  is cut off (`progress unkno`).
- Episode titles are truncated (`Nothing's Shoc…`, `The Trial of Ji…`, `They Did Wha…`).
- The status column does not line up from row to row, so the list looks ragged.

Seen with episodes S05E08–E12 while the card header showed IMPORTING, `4/12 downloaded · 0/12 ready`.
Viewport width not recorded.

The *progress unknown* text itself is a separate bug
([space-named files](2026-10-23-episode-progress-unknown-space-named-files.md)); this record is about the
layout, which needs to hold any status text (including future *Searching*, *Not found* and *Stalled*
labels from the feature) on one line without clipping.

The header showing IMPORTING while 8 of 12 episodes still download is covered by the feature's request
state rule (D), not by this record.

## Acceptance

Every episode row shows its full status on one line, titles are readable or truncate gracefully with
the full title available, and status labels line up across rows at the supported viewport widths.
