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

### 4. GRABBING State Should Show Episode Progress

**Current:** Shows single "Grabbing" badge with no episode count
**Wanted:** Show "Grabbing 3/12 eps" during the grab phase

**How Sonarr works:**
- Sonarr searches indexer per episode
- Accepts or rejects each episode individually
- This is ONE state (GRABBING), not separate SEARCHING/GRABBING

**Display requirements:**

| Location | Display |
|----------|---------|
| Card badge | "Grabbing 3/12" |
| Detail header | "Grabbing 3/12 episodes" |

**Episode-level display during GRABBING:**
```
S01E01  Spring and Hard Times    ✓ Grabbed
S01E02  A Handful of Sand        ✓ Grabbed
S01E03  Howling at the Moon      ✓ Grabbed
S01E04  Passing Shower           ⏳ Searching...
S01E05  Kokoro                   ○ Pending
```

**Implementation notes:**
- Track grabbed_count on MediaRequest or calculate from Episode states
- Episode states: PENDING → SEARCHING → GRABBED → DOWNLOADING
- Update count as each Sonarr grab webhook arrives

### 6. Timeline Downloading Event Should Show Size

**Current:** "Downloading: Tsukigakirei"
**Wanted:** "Downloading: Tsukigakirei - 78.2 GB"

Include file size in the downloading timeline event details.

### 7. Better Per-Episode Progress Display

**Current:** All episodes show same "Downloading" badge
**Wanted:** Show per-episode download % for season packs

For season packs (single torrent, multiple files):
- Use qBittorrent file progress API to get per-file %
- Display individual episode progress bars

Example:
```
S01E01  Spring and Hard Times    ████████████ 100%
S01E02  A Handful of Sand        ████████░░░░  67%
S01E03  Howling at the Moon      ████░░░░░░░░  33%
S01E04  Passing Shower           ░░░░░░░░░░░░   0%
```

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

### 7. Better Per-Episode Progress Display

**Current:** All episodes show same "Downloading" badge
**Wanted:** Show per-episode download % for season packs

For season packs (single torrent, multiple files):
- Use qBittorrent file progress API to get per-file %
- Display individual episode progress bars
- Show which episodes are complete vs still downloading

Example:
```
S01E01  Spring and Hard Times    ████████████ 100%
S01E02  A Handful of Sand        ████████░░░░  67%
S01E03  Howling at the Moon      ████░░░░░░░░  33%
S01E04  Passing Shower           ░░░░░░░░░░░░   0%
```

## Acceptance Criteria

- [ ] Timeline shows "Grabbed" (past tense) not "grabbing"
- [ ] Episode Progress shows "x downloaded, y ready" (not just "x ready")
- [ ] Episodes show download % when in DOWNLOADING state
- [ ] "Matching" replaced with "Downloaded" for anime TV shows (or hidden)
- [ ] (Optional) SEARCHING state shows while Sonarr searches indexers
- [ ] Grabbing state shows "Grabbing 3/12 episodes" for per-episode releases
- [ ] Timeline Downloading event shows file size
- [ ] Per-episode progress % for season packs (via qBit file API)
