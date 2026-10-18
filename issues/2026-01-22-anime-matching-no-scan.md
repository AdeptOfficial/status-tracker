# Issue: ANIME_MATCHING State Doesn't Trigger Jellyfin Scan

**Date:** 2026-01-22
**Severity:** High
**Status:** Open

---

## October 18 handoff — next DEV task

User is wrapping up tonight and requested documentation for a future agent.
No implementation of the following proposal has been made. Production remains
explicitly on hold. This is the next Status Tracker investigation.

### Verified evidence

- DEV request 20 / Sonarr series 51: The Greatest Demon Lord Is Reborn as a
  Typical Nobody S01, 12 episodes, TMDB120155 / TVDB402652.
- All 12 downloaded and imported as hardlinks after the scoped permission repair.
- Shoko file IDs323–334 each had one episode association for TMDB120155; queue
  had zero running/waiting/blocked work. Matching itself was complete.
- Jellyfin had no matching series and its Scan Media Library task was Idle.
- One manual DEV Jellyfin library refresh created the series and all12 episodes.
  Scan returned Idle; tracker automatically became Available with its Watch link.
- User explicitly confirmed playback works. No media/VFS deletion was needed.
- This demonstrates a refresh/handoff gap, not its precise cause. The January
  diagnosis/code snippets below are historical; inspect current code before fixing.
  Do not assume Shoko is broken or that a VFS rebuild is necessary.

### Proposed work for the next agent

1. Trace current Shoko match events, tracker correlation, scan scheduling and
   fallback recovery; establish why this completed match did not lead to a scan.
   Relevant files: app/clients/shoko.py, app/plugins/shoko.py,
   app/services/jellyfin_verifier.py, app/services/shokofin_vfs.py,
   app/clients/jellyfin.py. Inspect safe selected logs/fields, never credentials.
2. Queue a library refresh after confirmed matching, coalescing episode bursts
   and respecting an already-running scan. Add bounded retry/backoff and useful
   failure diagnostics; handle missed events/restarts without scan storms.
3. Consider a clear “Waiting for library refresh” presentation after confirmed
   matching. Do not infer matching from elapsed time or mark Ready until Jellyfin
   confirms playable episode availability. UI proposal is not implemented.
4. Add isolated tests for burst events, failed scans, retries, missed-event
   recovery, partial availability, duplicate events and restart behavior. Add a
   browser assertion for any new status text and live updates.
5. Validate automatic recovery on DEV without manually scanning; record evidence
   separately from the successful manual recovery and user playback above.
   Avoid another large download if existing DEV data can safely validate the flow.

### Starting state and guardrails

Latest DEV image: status-tracker:local-time-20261018 (app f58d078), with the
152-test import-evidence fix afc9772. Firefox suite passed local-time initial,
live-swap and reconnect checks. Existing warnings are documented in TESTING.md.
Backups/rollback: infra configs/dev/services/status-tracker/README.md.
Request20 force-start already removed; do not repeat its one-time data correction.
Read-only watcher stops on Available; it is no longer required for this completed
request. Temporary observation files may expire and are not the durable handoff.
Other old DEV torrents were not paused/unmonitored; do not alter them implicitly.
No production deployment, new article draft or publication is authorized here.
Related: 2026-10-17-dev-import-permissions.md and shared content backlog candidate
2026-10-17-status-tracker-episode-progress.

## Historical January report

## Problem

The fallback checker triggers Jellyfin library scans for requests in `IMPORTING` state but NOT for `ANIME_MATCHING` state. This leaves anime requests stuck.

## Code Location

`app/services/jellyfin_verifier.py:440-445`

```python
# Current code only triggers scan for IMPORTING
needs_scan = any(r.state == RequestState.IMPORTING for r in stuck_requests)
if needs_scan:
    await jellyfin_client.trigger_library_scan()
```

## Fix Needed

Also trigger scans for ANIME_MATCHING:

```python
needs_scan = any(r.state in (RequestState.IMPORTING, RequestState.ANIME_MATCHING) for r in stuck_requests)
```

## Impact

- Anime TV/Movie requests get stuck at ANIME_MATCHING indefinitely
- Requires manual Jellyfin library scan to proceed
- Breaks the "fully automatic" flow for anime content

## Affected Requests

- My Teen Romantic Comedy SNAFU - stuck at anime_matching
