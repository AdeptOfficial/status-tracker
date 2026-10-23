# TV request stops tracking downloads after the first episode finishes

**Created:** 2026-10-23
**Status:** Open (fix proposed against the current code 2026-10-23, not implemented)
**Severity:** High (multi-episode TV: progress, speed, ETA and episode completion freeze for the rest
of the download; the request card shows a wrong, stalled state)
**Found:** DEV regular-TV test, 2026-10-23 (Gotham S5, request 25: 12 episodes, one torrent each)
**Feature:** [per-episode progress and request state](../features/2026-01-18-per-episode-progress-and-request-state.md) (goal, evidence and the full proposed solution)
**Related:** [episode progress unknown](2026-10-23-episode-progress-unknown-space-named-files.md),
[downloaded state display](2026-01-22-downloaded-state-display.md)

## Problem

When the first of twelve episodes finished, the request moved to DOWNLOADED and stopped updating:

| Time (UTC) | Status Tracker | qBittorrent |
|---|---|---|
| 18:38:41 | request DOWNLOADED, progress 0.083 (1/12), speed and ETA cleared; 1 episode DOWNLOADED, 11 DOWNLOADING | first torrent complete |
| 18:40:31 | unchanged (last update 18:38:41) | 1 of 12 complete, 65% overall |
| 18:41:40 | unchanged (last update 18:38:41) | **2 of 12 complete**, 73% overall |

The second finished episode was never recorded, and the request card stays at about 8% with no
speed or ETA while eleven episodes keep downloading.

## More evidence (2026-10-23)

- **App log (DEV):** each Grab webhook logged `Created new episode S05E0x` with its own hash, and the
  poll logged `Episode S05E01..E12 -> downloading`. At 18:38:41 `Episode S05E03 -> downloaded` and
  `Request 25: downloading -> downloaded`; after that **no further qBittorrent poll lines** for this
  request, only the Jellyfin fallback checker (`not verified; retaining downloaded`) every 30 s.
- **Production history (older build, read-only):** the same pattern on real anime. Makeine (12 episodes,
  12 torrents) went DOWNLOADED at 1/12, recorded one import, and was marked AVAILABLE about three minutes
  after the first episode finished; Orb (25 episodes) the same at 1/25. Of 12 production anime requests,
  6 were one torrent per episode or mixed, so this affects about half of real anime requests.
- **Later the same day (DEV, Gotham):** with 6 episodes available and 6 still downloading, the request
  sat in IMPORTING (not refreshed because of bug 2) past the import time limit and the timeout checker
  moved it to **TIMEOUT**. E05 meanwhile stalled at 13% with 0 seeders (Sonarr status `warning`, still
  `downloading`), E10–E12 queued with no known seeders: real cases for goal 4 (per-episode Stalled)
  instead of a request-level timeout.
- qBittorrent's completion webhook is off on production too.
- Raw evidence: homeserver `notes/2026-10-23-dev-gotham-per-episode-tracking.json` (private).

## Cause

Three pieces of `app/plugins/qbittorrent.py` and `app/services/state_calculator.py` combine:

1. `calculate_aggregate_state()` shows the highest in-progress episode state, so one DOWNLOADED
   episode makes the whole request DOWNLOADED (by design).
2. `_recalculate_request_state()` then replaces the live, size-weighted torrent progress with the
   episode ratio (1/12) and clears speed and ETA, because the new state is past DOWNLOADING.
3. `_get_trackable_requests()` polls only requests in **GRABBING or DOWNLOADING**. From then on the
   request is skipped, so its remaining episodes are never polled again: no per-episode completion,
   no progress, no speed or ETA.

qBittorrent's run-on-completion webhook (`/hooks/qbittorrent`) would still mark episodes complete,
but it is not configured on DEV (`autorun_enabled` is false), so polling is the only source. A
single-torrent movie or season pack is unaffected: it finishes all at once.

What happens next, to be confirmed by watching this test: the remaining episodes stay DOWNLOADING
in the tracker until Sonarr's import webhooks move them on.

## Current code this fix touches (checked 2026-10-23)

- Schema needs **no change**: `episodes` already has `qbit_hash` (indexed), `state` and nullable
  `download_progress`; `requests` has `download_progress`, `download_speed`, `download_eta`. The
  migration mechanism (`database.py` `run_migrations`) only adds columns, so this matters.
- Three places filter on the **request** state GRABBING/DOWNLOADING, all in `app/plugins/qbittorrent.py`:
  `_get_trackable_requests()` (which requests are polled), `get_adaptive_poll_interval()` (`POLL_FAST` 3 s vs
  `POLL_SLOW` 15 s; the 5 s/30 s in the `main.py` docstring is stale) and, indirectly, `poll()` (request progress only from those requests).
- `poll()` builds each request's torrent list from `hash_to_episodes`, which holds only episodes still
  GRABBING/DOWNLOADING. So `_update_tv_progress_from_torrents()` weights progress over **active torrents
  only**: when an episode finishes, its torrent leaves the average. Even if polling continued, the
  request percentage would jump back to the remaining torrents' average after each completion.
- `_recalculate_request_state()` (line 422) and the completion webhook (`handle_webhook`, line 198) both
  overwrite request progress with `finished / total` and clear speed/ETA once the aggregate state is
  past DOWNLOADING.
- Episode completion itself (`_update_episode_progress`) uses the torrent state or 100% progress, not
  file matching, so it works as soon as the episode's hash is polled again.
- Sonarr's import webhook (`plugins/sonarr.py` `_handle_download`) sets each imported episode's state
  directly whatever the tracker held, so stalled episodes still move on at import.
- The existing test `test_poll_fetches_files_once_per_hash_and_persists`
  (`tests/test_episode_progress.py`) covers one shared hash (season pack) only; its fixtures
  (`MediaRequest`, `Episode`, `TorrentInfo`, mocked `get_torrents`/`get_files`) can be reused.

## Proposed fix (against the current code)

1. **Poll by episode, not by request state.** In `_get_trackable_requests()`, select requests that are
   GRABBING/DOWNLOADING **or** are TV with any episode GRABBING/DOWNLOADING that has a `qbit_hash`
   (an `exists()` subquery on `episodes`, or a join with `distinct()`). Movies unchanged.
2. **Same rule for the poll speed.** `get_adaptive_poll_interval()` counts the same set, so a partly
   downloaded TV request keeps fast polling.
3. **Request progress over all episodes, not active torrents.** For a TV request with episodes:
   `progress = (episodes past DOWNLOADING + sum of active episodes' progress) / episode count`, where an
   active episode's progress is its `download_progress` (file-level, from `file_progress()`), else its
   torrent's progress when that torrent maps to exactly one episode, else 0. Speed = sum and ETA = max
   over the active torrents, as now. This replaces both the active-only weighted average and the
   `finished / total` overwrite in `_recalculate_request_state()` and `handle_webhook`; clear speed and
   ETA only when no episode is GRABBING/DOWNLOADING. Season packs keep working: all their episodes
   share one hash and finish together.
4. **Decision for the owner (separate):** the Multi-Episode Tracking scope approved on 2026-10-17 says
   "existing state transitions are unchanged", so the card keeps showing DOWNLOADED once any episode
   finishes. Showing DOWNLOADING while episodes remain would need new transitions (DOWNLOADED →
   DOWNLOADING, IMPORTING → DOWNLOADING) and a scope change. Fixes 1–3 do not need it.
5. **Optional:** recommend qBittorrent's run-on-completion webhook in `docs/SETUP.md`.

## Tests to add (extend `tests/test_episode_progress.py`)

- Twelve episodes on twelve hashes: after one completes, the next poll still queries the other eleven
  and records the second completion; the request stays on fast polling.
- Request progress counts finished episodes as 100% and active ones at their own progress; it never
  drops when an episode completes; speed and ETA clear only when none is active.
- Season pack (one hash) and movies behave as today; the existing poll test still passes.

## Acceptance

Regressions pass with the new cases; on DEV, a multi-torrent TV request keeps live progress until the
last episode finishes and records every episode's completion without the qBittorrent webhook.
