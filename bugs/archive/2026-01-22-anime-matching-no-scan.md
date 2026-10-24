# Resolution — 2026-10-20

**Status: Resolved on DEV; production remains on hold.**

Automatic discovery verified on DEV: S1 reached Ready 10/10; user confirmed S1E1 playback. Persistent cache-before-scan recovery replaces the original one-line scan proposal.

See [current tests and limitations](../../docs/TESTING.md). The entries below
are chronological investigation history; earlier pending statements are superseded.

---

## October 20 — real DEV flow verified: Cyberpunk S1 Ready, S2 separate

At14:50:24 UTC, tracker21/Jellyseerr151 reached AVAILABLE with10/10 S1 episodes.
Tracker22/Jellyseerr150 remained APPROVED for S2, with no download or episode rows.
All ten new files downloaded, imported as hardlinks (nlink2), matched in Shoko,
were discovered by automatic recovery and verified in Jellyfin. Independent
read-only real-API checks in a disposable database found10 Shoko matches and10
playable episodes with zero unnecessary scans. A one-byte read from each actual
VFS video path inside Jellyfin succeeded. User playback itself was not tested.

The decisive automatic sequence: ShokoClearPluginCache completed at14:49:25.042
UTC; library scan started14:49:25.247 and completed14:49:38.576. No manual scan,
VFS/media deletion for recovery, retry-budget reset, or direct Ready update.
The earlier metadata-task attempt failed; the exact installed plugin source and
VFS preview identified stale in-memory generation data (38 old vs48 expected
files). Current recovery waits for memory-cache clearing to finish before scanning.

Final DEV image `status-tracker:cache-20261020`;192 regressions pass in that image.
Permanent Firefox acceptance passes season navigation/live updates; final real
DEV home and both detail pages pass320/390/768/1440/2048px. Existing test warnings
remain. Current rollback `status-tracker:before-cache-20261020` is the preceding
metadata-recovery build; the stable season-only fallback is
`status-tracker:seasons-20261020`. Stopped-app backups are retained under
`/opt/backups/status-tracker-before-cache-20261020` and the prior release folders.

DEV free space18.05 GiB. Earlier authorized Kaguya removal reclaimed12.53 GiB;
active test media and request20 were preserved. Watcher stopped after observing
all10 episodes AVAILABLE. Refresh jobs retire on their next scheduled check
without another scan once availability is verified. Production untouched by this
work. Source remains uncommitted; content candidate remains deferred/unpublished.

## October 20 — current DEV cache recovery correction

Current image `status-tracker:cache-20261020`; rollback
`status-tracker:before-cache-20261020`; stopped data/source backup
`/opt/backups/status-tracker-before-cache-20261020`. 192 isolated regressions pass
in the runtime image. Startup health passes; UI from the season release retained.

The metadata-task hypothesis below was disproved on the installed Shokofin
6.0.5.11: its task completed at14:43:39 UTC but still no Cyberpunk series appeared.
Exact-version source shows AutoRefresh updates existing library entities only and
must not overlap a library scan. Removed that recovery dispatch. The VFS preview
instead saw48 files versus38 existing, including the ten new Cyberpunk files,
while ordinary scans kept the cached structure. Shoko SignalR is Connected.

Recovery now discovers ShokoClearPluginCache by exact task key, requires library,
metadata and cache tasks Idle, clears only plugin memory caches, confirms a new
Completed task result, then starts a library scan. Unknown/missing/busy/failed
states prevent scanning. Attempts remain bounded/persisted; no media or VFS
entries are directly deleted and no manual scan or job-budget reset was used.
Real playable verification remains pending the existing automatic retry schedule.

Source inspected at tag v6.0.5-dev.11:
https://github.com/ShokoAnime/Shokofin/blob/v6.0.5-dev.11/Shokofin/Tasks/ClearPluginCacheTask.cs
https://github.com/ShokoAnime/Shokofin/blob/v6.0.5-dev.11/Shokofin/Events/MetadataRefreshService.cs

## October 20 — separate season identity and Shokofin discovery (DEV)

Current DEV image: `status-tracker:discovery-20261020`; rollback:
`status-tracker:before-discovery-20261020`. Backup:
`/opt/backups/status-tracker-before-discovery-20261020` (stopped data/source).
189 isolated regressions pass in the exact runtime image. Firefox acceptance
passes related-season labels/navigation, SSE and responsive layouts; real DEV
home and requests21/22 pass at 320/390/768/1440/2048px.

New Jellyseerr TV request IDs remain distinct. Sonarr correlation includes season;
ambiguous provider-only matches fail closed. TV Jellyfin/Jellyseerr availability
notifications use per-episode verification. Related seasons share an active card
and link to separate detail timelines/progress. Backed-up live repair retained
S1 tracker21's ten episodes/history, assigned Jellyseerr151, and restored S2 as
tracker22/Jellyseerr150 Approved. Audit events explain the original mixed history.

Real S1 download/import completed; all ten files are hardlinked and Shoko-matched.
Standard automatic Jellyfin scans alone did not discover the series. Installed
ShokoAutoRefreshMetadata task had last run in January. Recovery now discovers its
ID by exact key and invokes it after an accepted library scan, within the existing
persisted retry budget/backoff. Running tasks are not restarted; missing/failed
metadata refresh is recorded. No VFS deletion or manual scan. Actual playable
Jellyfin verification is still pending; do not call end-to-end flow passed yet.
DEV has about18.2 GiB free after authorized removal of older Kaguya media.
Production and publication remain user-gated.

# Issue: ANIME_MATCHING State Doesn't Trigger Jellyfin Scan

**Date:** 2026-01-22
**Severity:** High
**Status:** Open

---

## 2026-10-20: Review findings fixed and redeployed to DEV

- Fixed wrong-season readiness: verification now strictly filters the requested
  season, including season0, without the display helper's fallback to other rows.
- Missed-event recovery confirms the current file before deduplicating by file ID.
  An old job no longer blocks replacement files; the same file's terminal status
  and retry budget remain unchanged.
- Verification failures now roll back only that request's uncommitted changes,
  defer its jobs with `verification_failed`, reload expired ORM state and continue
  unrelated requests. Successful request changes commit independently.
- Seven permanent review regressions cover wrong-season/specials, replacement
  files, terminal-job deduplication and failure isolation in either request order,
  including rollback of flushed mutations. Full suite:177 pass, also in the exact
  release image (1470 existing warnings). Permanent Firefox acceptance passes.
- DEV image `status-tracker:refresh-review-20261020`; rollback image
  `status-tracker:before-refresh-review-20261020`. Fresh stopped-app backup:
  `/opt/backups/status-tracker-before-refresh-review-20261020` (data/source).
  No schema change in this follow-up. Existing Compose/secrets/data preserved.
- Real APIs again verify request20's 12 Shoko matches and 12 playable episodes
  using a disposable tracker DB; no scan or live data changes. Original tables
  match backup, integrity/health pass. Next normal import remains the unattended
  discovery acceptance test, as chosen by the user. Production unchanged.

## October 20 — implemented on DEV, new-import observation pending

The old fallback called SSH to inspect/delete VFS entries, but the deployed image
had no SSH executable. October18 retained logs show nine check and nine rebuild
errors (errno2). This explains fallback failure, not why Shokofin originally
missed discovery. The old January one-line scan proposal is superseded.

## 2026-10-20: Persistent automatic library refresh on DEV

- Replaced the automatic SSH/VFS-delete fallback with durable refresh intents,
  confirmed Shoko event/path evidence, a 30-second debounce and one API scan per
  due batch. Existing scans are respected; minimum spacing is 120 seconds, with
  four persisted attempts and exponential backoff. Duplicate evidence never
  resets the budget. Exhausted jobs retain diagnostic codes; no automatic retry
  reset is provided. The deployment uses one fallback worker.
- Missing SignalR events can be recovered from imported paths through Shoko's
  installed v3 PathEndsWith API. Ambiguous, inaccessible and unassociated files
  do not queue refreshes. An ID or elapsed time alone is not match evidence.
- TV verification now checks playable season/episode entries rather than treating
  a series directory as proof that an entire season is ready. Partial seasons and
  metadata-only episodes stay incomplete; known missing episode rows block Ready.
- 170 isolated regressions pass, including full missed-event → automatic scan →
  Available recovery with mocked service boundaries. All 170 also pass in the
  exact deployment image; existing deprecation/async warnings remain (1416 there).
  Permanent Firefox acceptance passes SSE/reconnect, local time, History and
  320/390/768/1440/2048px layouts.
- DEV image `status-tracker:refresh-20261020`, rollback `status-tracker:before-refresh-20261020`.
  Backup `/opt/backups/status-tracker-before-refresh-20261020` contains stopped-app
  data and prior app source. Additive `library_refresh_jobs` table only. All prior
  rows unchanged (11 requests, 37 episodes, 71 timeline events, 68 deletion logs,
  716 deletion-sync events), integrity OK, health/database/Shoko connected.
- A disposable in-memory tracker using real DEV APIs confirms all 12 Shoko matches
  and playable Jellyfin episodes for request 20, with zero unnecessary scans and
  no live data changes. This is not proof of discovery after a fresh import.
  User chose deployment now and observation on the next normal request; no new
  download, media deletion, manual scan, production deployment or publication.
- Initial deployment-script extraction hit the DEV Python version's unsupported
  tar filter argument; rollback restarted the old image. Retried with validated
  archive paths and existing backup; final deployment succeeded.

Acceptance on the next normal request:
1. Confirm Shoko match associations and imported paths.
2. Observe `library_refresh_jobs` progress and `[LIBRARY REFRESH]` diagnostics.
   A 30s debounce precedes dispatch; scans have a 120s global minimum interval,
   four attempts and exponential backoff. Active Jellyfin scans defer dispatch.
3. Confirm actual playable Jellyfin episodes and correct partial/ready counts.
4. Do not press Scan to make the test pass. Record natural recovery, failed
   attempts or exhaustion. Investigate exhausted rows rather than deleting them
   to reset the retry limit. Duplicate events must not reset attempts.

Limits: full-library refresh is used, as with the existing Jellyfin API client.
A single fallback worker owns dispatch. Retry evidence is deduplicated per
request/episode/file; deliberate re-import of the same file after exhausted/done
work needs an explicit future retry/reset design. Unknown Shoko path mappings
remain pending rather than being guessed. No new waiting-status UI was added.

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
