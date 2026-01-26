# UI Bug: Episode Status Inconsistency

**Date:** 2026-01-25
**Status:** Open
**Severity:** Low (cosmetic)

## Description

Episode Progress section shows inconsistent status across episodes during download:
- Header shows "Downloading 12/12 eps"
- Some episodes show "Matching" (e.g., S01E01, S01E02)
- Other episodes show "Grabbed" (e.g., S01E03-E06)
- Progress bar shows mixed colors (orange for Matching, cyan for Grabbed/Downloading)

## Expected Behavior

During a season pack download:
- All episodes should show consistent "Downloading" status
- OR status should accurately reflect per-episode state from Sonarr

## Actual Behavior

Mixed statuses displayed simultaneously, confusing user about actual download state.

## Root Cause (Suspected)

When downloading a season pack, Sonarr may report different statuses per episode based on:
- Whether the episode file has been matched in the pack
- Import order within the pack
- Shoko matching running in parallel

## Steps to Reproduce

1. Request an anime series (e.g., "My Tiny Senpai")
2. Wait for Sonarr to grab a season pack
3. Observe Episode Progress section during download

## Screenshots

User-provided screenshot shows:
- S01E01: Matching
- S01E02: Matching
- S01E03-E06: Grabbed
- Header: "Downloading 12/12 eps"

## Suggested Fix

Consider:
1. Show overall download progress for season packs instead of per-episode status during download
2. Only show per-episode status after import begins
3. Add tooltip explaining the mixed states
