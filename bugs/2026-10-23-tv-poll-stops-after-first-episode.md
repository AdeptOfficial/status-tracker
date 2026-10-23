# TV request stops tracking downloads after the first episode finishes

**Created:** 2026-10-23
**Status:** Open (fix proposed, not implemented)
**Severity:** High (multi-episode TV: progress, speed, ETA and episode completion freeze for the rest
of the download; the request card shows a wrong, stalled state)
**Found:** DEV regular-TV test, 2026-10-23 (Gotham S5, request 25: 12 episodes, one torrent each)
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

## Proposed fix

1. **Track by episode, not by request state.** In `_get_trackable_requests()`, select TV requests that
   have any episode in GRABBING or DOWNLOADING with a `qbit_hash`, whatever the request's own state
   (movies keep the current GRABBING/DOWNLOADING filter). The hash map already only includes those
   episodes, so nothing else changes there.
2. **Keep live progress while anything is still downloading.** In `_recalculate_request_state()` (and
   the matching block in the completion handler), switch to the episode ratio and clear speed and
   ETA only when no episode is GRABBING or DOWNLOADING; otherwise leave the torrent-weighted values
   from `_update_tv_progress_from_torrents()`.
3. **Decision for the owner (separate):** whether a partly downloaded TV request should show
   DOWNLOADING rather than DOWNLOADED while episodes remain, i.e. rank DOWNLOADING above DOWNLOADED in
   `calculate_aggregate_state()` when both are present. Fixes 1 and 2 work either way.
4. **Optional:** document that the qBittorrent completion webhook is recommended (it removes the
   dependence on polling), in `docs/SETUP.md`.

## Tests to add

- A TV request with 12 episodes on separate hashes: after one completes, the next poll still queries
  the other 11 hashes and records the second completion.
- Progress stays torrent-weighted (not 1/12) with speed and ETA while any episode downloads; switches
  to the episode ratio and clears speed/ETA when none remain.
- Movies and season packs unchanged.

## Acceptance

Regressions pass with the new cases; on DEV, a multi-torrent TV request keeps live progress until the
last episode finishes and records every episode's completion without the qBittorrent webhook.
