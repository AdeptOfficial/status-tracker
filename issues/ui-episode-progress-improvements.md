# UI: Episode Progress Display Improvements

**Created:** 2026-01-22
**Status:** Open
**Priority:** Medium
**Component:** UI (detail.html, card.html)

## Context

Per-episode tracking is implemented, but the UI needs improvements to better communicate episode states and progress.

## Requested Changes

### 1. Timeline: "grabbing" Should Be "Grabbed"

**Current:** Timeline shows "grabbing" (present tense)
**Wanted:** Show "Grabbed" (past tense) - the event appears AFTER grab is complete

The timeline event is logged after Sonarr confirms the grab, so it should use past tense to indicate completion.

### 2. Episode Progress Summary Should Show Downloaded Count

**Current:** Only shows "x/13 ready"
**Wanted:** Show "x/13 downloaded" and "x/13 ready" separately

Example:
```
Episode Progress          3/12 downloaded, 0/12 ready
```

### 2. Remove "Matching" Label for Anime TV

**Current:** After download completes, anime shows "Matching" state
**Wanted:** Show "Downloaded" instead - matching happens in background, user doesn't need to see it as primary state

The state machine has ANIME_MATCHING but the UI label should be friendlier.

### 3. Per-Episode Download Percentage

**Current:** Episodes show state badge only (e.g., "Downloading")
**Wanted:** Show download % per episode when downloading

Example:
```
S01E01  Lonely Rolling Bocchi    Downloading 45%
S01E02  See You Tomorrow         Downloading 12%
S01E03  Be Right There           Pending
```

**Note:** For season packs, all episodes share the same qbit_hash and progress. Could show same % for all, or show "Downloading (pack)" to indicate shared progress.

**Reference:** MVP.md states "TV: Show episode counts ('3 downloaded, 5 downloading, 4 queued')"

### 4. New State: SEARCHING (Sonarr searching indexers)

**Current:** Request stays at APPROVED while Sonarr searches
**Wanted:** New SEARCHING state to show "Searching indexers..."

**User sees:** Jellyseerr toast saying "Searching indexers for [BOCCHI THE ROCK! : S01E11]" but dashboard shows nothing happening.

**Proposed state flow:**
```
APPROVED -> SEARCHING -> GRABBING -> DOWNLOADING -> ...
```

**Implementation notes:**
- Sonarr doesn't send a webhook when starting search
- Could trigger SEARCHING when request is created and Sonarr has the series
- Or, add polling to detect when Sonarr is actively searching
- Alternative: Skip this state if too complex, just improve messaging at APPROVED

## Files to Modify

| File | Change |
|------|--------|
| `app/templates/detail.html` | Episode progress summary, per-ep % |
| `app/templates/components/card.html` | Episode progress summary |
| `app/models.py` | Add SEARCHING state (if implementing) |
| `app/schemas.py` | Update state labels |

## Related Issues

- `issues/per-episode-download-tracking.md` - Original per-episode feature (data model)
- `features/status-dashboard-multi-episode-tracking.md` - Multi-episode UI spec

## Screenshots

- Image #7: Jellyseerr shows "Searching indexers" - no equivalent in status-tracker
- Image #8: Detail page during download - good, but missing downloaded/ready counts

## Acceptance Criteria

- [ ] Timeline shows "Grabbed" (past tense) not "grabbing"
- [ ] Episode Progress shows "x downloaded, y ready" (not just "x ready")
- [ ] Episodes show download % when in DOWNLOADING state
- [ ] "Matching" replaced with "Downloaded" for anime TV shows (or hidden)
- [ ] (Optional) SEARCHING state shows while Sonarr searches indexers
