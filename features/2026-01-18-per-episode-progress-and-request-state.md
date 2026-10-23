# Per-episode progress and request state for TV and anime

**Created:** 2026-01-18 (as "Status Dashboard: Multi-Episode Tracking"; renamed and rewritten 2026-10-23)
**Component:** status-tracker
**Priority:** High
**Status:** Partially implemented on DEV (2026-10-17 scope); first real tests on 2026-10-23 found two
bugs; target behaviour agreed with the owner 2026-10-23; not yet implemented
**Bugs:** [TV request stops tracking after the first episode](../bugs/2026-10-23-tv-poll-stops-after-first-episode.md),
[episode progress unknown for space-separated names](../bugs/2026-10-23-episode-progress-unknown-space-named-files.md)
**Related:** [airing anime pending episodes](../issues/2026-01-26-pending-episodes-airing-anime.md),
[episode progress UI improvements](../issues/2026-01-22-ui-episode-progress-improvements.md),
[per-episode download tracking (January plan)](2026-01-18-per-episode-download-tracking.md)

## Goal (agreed 2026-10-23)

One rule for every request with two or more episodes, TV or anime, whether the episodes arrive as one
season pack, one torrent per episode, or a mix:

1. **One progress bar per episode**, each with its own state.
2. **The request stays DOWNLOADING until every episode it waits for has reached DOWNLOADED**; only then
   does the request move to DOWNLOADED. Episodes that finish early may already import or become
   ready, shown on their own rows.
3. **Searching / not found:** every requested episode has a row from the start. An episode with no
   download yet shows *Searching*; after a time limit with nothing grabbed it shows *Not found*. The
   request is not complete while an episode is missing.
4. **Stalled, per episode:** an episode whose download stops progressing shows *Stalled* on its own row
   (for example "E07 · stalled · 45%"); the request stays DOWNLOADING with a "1 stalled" note and the
   other episodes are unaffected. It clears by itself when the episode moves again.

| Release shape | Bars | Episode state | Request state |
|---|---|---|---|
| Season pack, `SxxEyy` file names | one per episode (file progress) | all → DOWNLOADED together when the torrent completes (the pack imports as a whole) | DOWNLOADING → DOWNLOADED once |
| Season pack, absolute names (`[Group] Show - 01.mkv`) | one per episode once files can be mapped (see C2); one pack bar until then | as above | as above |
| One torrent per episode | one per episode (that file's progress) | each → DOWNLOADED on its own | DOWNLOADING until the last episode is DOWNLOADED |
| Mixed (pack plus single episodes) | per episode where mappable | per torrent | DOWNLOADING until all are DOWNLOADED |

Out of this feature: a new episode grabbed after the request finished (weekly airing anime) is the
[airing anime issue](../issues/2026-01-26-pending-episodes-airing-anime.md).

## Current state and evidence (2026-10-23)

The 2026-10-17 scope below shows per-episode progress from qBittorrent file data and was verified with
synthetic tests only. The first real requests:

- **DEV, Gotham S5 (12 episodes, one torrent each, space-separated names):** each Grab webhook created
  its episode row with its own torrent hash, and the poll moved all twelve to downloading. Every episode
  showed *progress unknown* (bug 1). When the first episode (E03) finished, the request became DOWNLOADED
  at 1/12 and the poll stopped following it; three minutes later qBittorrent had 2/12 done and 73%
  while the tracker still showed 1/12 at 8% with no speed (bug 2). Each later Grab webhook also logged a
  harmless *invalid transition downloading → grabbing* warning.
- **DEV anime packs** (Cyberpunk S1/S2, Demon Lord) ended with every episode at 100%, but only the final
  value was stored, so live per-episode progress in packs is not yet proven on a real download.
- **Production (older build, read-only):** of 12 anime requests, 5 were packs, 4 one torrent per episode
  and 2 mixed. Per-episode requests were marked AVAILABLE after the **first** episode (Makeine: 1 of 12;
  Orb: 1 of 25), with only one import recorded. The DEV build requires verified episodes for TV
  availability; that is still to be confirmed on a per-episode request (Gotham's import phase).
- qBittorrent's run-on-completion webhook is off on DEV and production, so polling is the only source
  of completion.

Raw evidence (private infrastructure notes): `notes/2026-10-23-dev-gotham-per-episode-tracking.json` in
the homeserver repository.

## Proposed solution, against the current code (2026-10-23)

No change to the existing tables is required for A–C; D and E add nullable columns, which the add-only
migration in `app/database.py` (`run_migrations`) supports.

**A. Follow every downloading episode** ([bug 2](../bugs/2026-10-23-tv-poll-stops-after-first-episode.md))
- `app/plugins/qbittorrent.py` `_get_trackable_requests()`: also select TV requests with any episode
  GRABBING/DOWNLOADING that has a `qbit_hash`, whatever the request state. `get_adaptive_poll_interval()`
  counts the same set so fast polling (3 s) continues.
- Request progress over all episodes: (episodes past DOWNLOADING + sum of active episodes' progress) /
  episode count; speed = sum and ETA = max over active torrents. Replaces the active-torrents-only
  average and the `finished / total` overwrites in `_recalculate_request_state()` and `handle_webhook()`.

**B. One-episode torrents use their file's progress**
- `app/services/episode_progress.py` `file_progress()`: when a torrent maps to exactly one tracked episode
  and holds one video file, use that file's progress if the file name has no `SxxEyy` marker **or** its
  marker equals that episode (today only the no-marker case is allowed). Covers Gotham-style and
  absolute-numbered anime per-episode releases without parsing.

**C. File-to-episode matching in packs**
- C1 ([bug 1](../bugs/2026-10-23-episode-progress-unknown-space-named-files.md)): the multi-episode guard
  must not read ` 1080p`, ` 720p` or a year after `SxxEyy` as a second episode.
- C2, absolute-numbered packs: ask Sonarr to parse each file name (`GET /api/v3/parse?title=…`), which
  uses Sonarr's own import logic including anime absolute numbering; cache the result per torrent hash.
  `app/clients/sonarr.py` has the client but no parse call yet. **To verify** with real anime file names
  before relying on it.

**D. Request state rule (goal 2)**
- `app/services/state_calculator.py` `calculate_aggregate_state()`: while any episode is GRABBING or
  DOWNLOADING, the request is DOWNLOADING (GRABBING if none has started), even if other episodes are
  further along. Applied from the first grab, the request never has to move backwards, so no new
  transitions are needed. This changes the 2026-10-17 statement "existing state transitions are
  unchanged" and is approved by the owner as the target.

**E. Searching / not found and stalled (goals 3 and 4)**
- Searching: when a TV request is approved, create an episode row per requested episode from Sonarr's
  episode list (`/api/v3/episode`, already used by `get_episode_count()`), with no `qbit_hash`. A row
  without a hash displays *Searching*; after a time limit *Not found*. Grab webhooks then fill the
  existing row instead of creating one. To decide in implementation: whether this needs an episode
  state value or stays a display rule on rows without a hash (preferred: display rule).
- Stalled: nullable `episodes.stalled_since`, set by the poll when the episode's torrent is `stalledDL`
  or its progress has not changed for a time limit (proposed 30 minutes), cleared when it moves. The
  episode stays DOWNLOADING; only the display changes. No new state-machine state.

**F. Housekeeping found on the way** (separate small records): the repeated *downloading → grabbing*
warning on each Grab webhook; DEBUG library logging without log rotation on DEV.

## Tests to add (`tests/test_episode_progress.py` and state tests)

- Twelve episodes on twelve hashes: after one completes, polling continues, the second completion is
  recorded, progress never drops, the request stays DOWNLOADING until the twelfth (D).
- One-episode torrent with a matching, missing and conflicting `SxxEyy` marker (B).
- Space-separated, underscore and dotted names; ranges still skipped (C1).
- Mixed: a pack plus single-episode torrents in one request.
- Requested episodes without a grab show Searching, then Not found after the limit (E).
- A stalled torrent marks only its episode; progress resumes and clears it (E).
- Existing season-pack and movie behaviour unchanged.

## Acceptance

On DEV, a real one-torrent-per-episode request and a real season pack each show per-episode progress
from grab to DOWNLOADED, the request stays DOWNLOADING until the last episode is downloaded, and every
episode reaches its correct final state; a missing and a stalled episode are shown on their own rows.

## History

### Problem

The status dashboard currently tracks only a single episode's status, even when a TV series request involves multiple episodes or seasons. This creates confusion for users who can't see the full download progress.

**Screenshot shows:**
- SPY x FAMILY request shows "Season 2, Episode 12" in sidebar
- Timeline shows "Found" event only for S02E01
- Progress bar shows 0.0% with no context on what's being tracked
- No visibility into other episodes in the queue

### Expected Behavior

1. **Episode list view** - Show all episodes being downloaded for a series request
2. **Per-episode progress** - Individual progress bars or status indicators for each episode
3. **Aggregate progress** - Overall completion percentage (e.g., "12/25 episodes downloaded")
4. **Clear status labels** - Users should understand what stage each episode is in:
   - Searching
   - Found (with release info)
   - Downloading (with %)
   - Importing
   - Available

### Proposed UI Improvements

```
Current Status: Downloading
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Overall: 3/25 episodes (12%)

Season 1:
  ├─ E01-E12: ✓ Available
Season 2:
  ├─ E01: ↓ Downloading (45%)
  ├─ E02: ↓ Downloading (12%)
  ├─ E03: 🔍 Searching...
  └─ E04-E12: ⏳ Queued
```

### Technical Considerations

- Sonarr API provides episode-level status via `/api/v3/episode?seriesId=X`
- qBittorrent can report per-torrent progress
- May need to correlate torrent files to episode numbers
- Season packs vs individual episode downloads have different tracking needs

### Deletion Verification for Multi-Episode Content

When deleting a TV series (especially anime), verification needs to account for multiple files:

**Current limitation:**
- Deletion sync deletes at series level (Sonarr series ID, Shoko series ID)
- No verification that individual episode files were actually removed
- No feedback on partial deletions (e.g., some episodes deleted, others failed)

**Needed improvements:**

1. **Pre-deletion inventory**
   - Query Sonarr for episode count before deletion
   - Query Jellyfin for episode items under the series
   - Store expected file count in DeletionLog

2. **Post-deletion verification**
   - Verify all episode files are gone from disk
   - Verify all episodes removed from Jellyfin library
   - Report partial failures (e.g., "Deleted 23/25 episodes, 2 failed")

3. **Shoko-specific considerations**
   - Shoko detects deletions via file system scans, not API calls
   - May need to trigger rescan and wait for completion
   - Verify AniDB entries are unlinked

**Proposed DeletionLog enhancements:**
```python
# Additional fields for multi-file tracking
episode_count: int           # Total episodes in series
episodes_deleted: int        # Successfully deleted
episodes_failed: int         # Failed to delete
partial_deletion: bool       # True if some episodes remain
```

**UI improvements for deletion logs:**
```
Charlotte (2015) - COMPLETE
├─ Episodes: 13/13 deleted
├─ Sonarr: ✓ Series removed
├─ Shoko: ✓ Series unlinked
├─ Jellyfin: ✓ 13 episodes removed
└─ Jellyseerr: ✓ Request cleared
```

### Related

- `ideas/features/2026-01-17-request-status-dashboard.md` - Original feature spec
- `apps/status-tracker/` - Current implementation

### Approved October 17 implementation scope

Keep FastAPI/SQLite/Jinja/HTMX/SSE. Show season-scoped downloaded and ready counts
on cards and detail; ready remains based only on AVAILABLE. Store nullable episode
progress and obtain it from qBittorrent file data, once per active hash per poll.
Only unambiguous video filenames with SxxExx markers are matched; a single video
and single distinct tracked episode can use that file's progress. Ambiguous,
unsupported, skipped or missing files remain unknown. No torrent-wide percentage
is copied to season-pack episodes. Existing state transitions are unchanged.
Additive SQLite migration preserves existing data; re-grabs clear old progress.
Tests must cover mapping, invalid data, migration, mixed seasons/states, rendering,
API persistence and repeatable browser updates/reconnection with synthetic data.
No new SEARCHING state, deletion behavior, or media download is in this iteration.

#### Verification and remaining scope

Approved October 17 scope implemented and deployed to DEV. 111 regressions and
permanent Firefox acceptance pass; see `docs/TESTING.md`. Real pipeline observation
awaits an active dev request. Multi-season grouped UI, deletion verification,
absolute-numbered anime pack matching, and a new SEARCHING state remain outside
this iteration. Production unchanged.
