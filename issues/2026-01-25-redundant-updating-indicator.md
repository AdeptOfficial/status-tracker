# Issue: Redundant "Updating..." Text When Live Updates Active

**Date:** 2026-01-25
**Severity:** Low (UX polish)
**Status:** PENDING
**Type:** UI fix

---

## Problem

The detail page shows both:
1. "Updating..." text (top right, with spinner)
2. "Live updates active" indicator (green dot)

This is redundant. If live updates are active, the user already knows the page is updating.

## Expected Behavior

When SSE is connected and live updates are active:
- Show only "Live updates active" (green indicator)
- Remove the "Updating..." text/spinner

The "Updating..." indicator should only appear during manual refresh or initial page load, not during SSE live updates.

## Files to Check

- `app/templates/detail.html` - SSE event handling
- `app/templates/base.html` - Update indicator component

## Screenshot

Shows "Updating..." in top right while also having live updates indicator.
