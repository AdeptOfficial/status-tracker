# Current validation — 2026-10-20

226 isolated regressions pass, including the exact deployed runtime image.
Permanent Firefox acceptance passes live updates/reconnect, season navigation,
local timestamps, History filters and responsive layouts. DEV Cyberpunk S1
completed automatic discovery with10/10 Ready; all ten video paths were read
inside Jellyfin, and the user confirmed S1E1 playback. S2 remains Approved.

Run `./run_tests.sh -q --disable-warnings`, then `./run_browser_tests.sh`.
The suites use synthetic data; never mount server secrets or live databases.
The runtime-image and live checks are recorded in the diary. Existing warnings
remain. S2 import, regular-media request flows, a fresh re-request, TV/anime
removal and physical-device/proxy coverage remain separate validation work.

Movie deletion now has a separate live pass: Interstellar audit70 verified actual
file and library absence, cleared service records and preserved all other tracker
states. Old failed audit69 remains in history. A new request/download was not
submitted. See [permission setup and evidence](MEDIA-PERMISSIONS.md).
The disposable preflight was tested for denied access, shared-group success,
root rejection, existing-file preservation and cleanup, then passed on DEV.
A separate isolated cross-writer test verified setgid/umask002 inheritance and
rename/deletion between UID911 and UID1000 in shared GID1000.
Current image `status-tracker:verified-delete-20261020`; nullable retry-path
migration and existing-data persistence are covered.

The sections below are chronological evidence. Older counts, images and pending
statements describe earlier builds and are superseded by this current summary.

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

# Status Tracker testing

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


## Latest DEV import validation (October 17)

152 isolated regression tests passed (1308 existing warnings). Added six cases
retaining unverified stages across anime/non-anime, verified availability recovery,
and completed-TV speed/ETA cleanup without a state change.
Real request 20: Sonarr 12/12 imported after the destination permission repair;
all files hardlinked, tracker 12/12 Matching, speed/ETA cleared. Shoko processing
observed. Jellyfin readiness and user playback are still pending.

## Regression suite

```sh
./run_tests.sh -q
```

Requires Docker. Builds the Python 3.12 test image, then runs pytest with networking
**disabled**. Fixtures use isolated SQLite and mocked media services. No app `.env`,
server credentials, or live data are mounted. For focused checks:

```sh
./run_tests.sh tests/test_episode_progress.py -q
```

October 17 result: **111 passed**, including 20 episode-progress cases added to the
existing 91 tests. The deployment image passed the same suite on DEV LXC 220 via
`python -m pytest` (its image does not include the pytest executable wrapper).
Existing deprecation/async-cleanup warnings remain: 869 warnings on this run.
They are not treated as errors; passing tests are not a claim those warnings are fixed.

## Local-time regression (October 18)

Firefox runs with TZ=America/Chicago and checks browser-local timeline text on
initial load, live HTMX replacement and after reconnect. Full browser suite passed.
The DEV fix runs timestamp conversion after htmx:afterSwap as well as initial load.

## Real browser suite

Requires Docker, Python 3, Node (tested with 25), Firefox, and curl. Node is only
used by the test runner, not the deployed app. After building the test image above:

```sh
npm --prefix tests/browser ci --ignore-scripts
./run_browser_tests.sh
```

The runner starts a localhost-only synthetic instance with temporary SQLite,
current app source mounted read-only, and no production polling/integrations.
The fixture routes under `/test/` exist only in this test instance; the production
Dockerfile copies only `app/`. Firefox uses a disposable profile. The runner
removes its test container even on failure. It restarts only that instance to
exercise SSE recovery. Output screenshot: `tests/browser/result.png` (ignored).
The app currently loads HTMX from unpkg; browser acceptance requires that CDN.

Checks include:
- Movie progress, speed, ETA and timeline updates without page reload.
- SSE reconnection after a server restart and a subsequent update.
- Ready to Watch state transition without refresh.
- Season-scoped downloaded/ready counts and known/unknown episode percentages.
- Episode updates through SSE, persisted values after reload, card/detail agreement.
- Detail-page layout at 390px phone width.

All checks passed October 17. This uses synthetic events and the actual routers,
broadcaster and templates. It does not establish current end-to-end qBittorrent,
Sonarr, Shoko or Jellyfin behavior, physical-phone usability or proxy behavior.

## Episode progress semantics

Downloaded includes downloaded, importing, anime matching/match failed and ready
states, plus a downloading episode whose matched file reports exactly 100%.
Ready includes only AVAILABLE. Existing lifecycle transitions remain unchanged.
Counters use the existing season scoping helper and denominator max(metadata,
tracked rows); its legacy fallback to all rows when no season matches is retained.
Percentage observations are stored as nullable floats and exposed in the API.
A new grab clears an old percentage. File-query failure produces unknown progress.

The qBittorrent files API is queried once per tracked hash per poll. Matching uses
unambiguous SxxExx video basenames, or one video for one distinct tracked episode.
Duplicate files, combined/range names, skipped files, invalid fractions and
unsupported multi-file names remain unknown. Absolute-numbered anime season
packs are not inferred. 99.99% is displayed as 99%, not 100%. Per-file percentages
never mark an episode playable. No torrent-wide percentage is copied to each file.
API reference: [qBittorrent torrent contents](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-4.1%29#get-torrent-contents).

## Dev review

DEV only: http://10.0.2.20:8100. Existing completed requests show the new summaries;
for example `/request/17` and `/request/10`. There are no active dev downloads, so
live partial-file behavior has only been tested with fixtures. No new download
was initiated. Production is unchanged and requires separate explicit approval.
Deployment/backup/rollback details are recorded in the homeserver service README.

## Real dev visual review follow-up

User said the desktop screenshot looks good. Read-only Firefox review of DEV
request 17 confirms 13 unique S01 episodes, all AVAILABLE, and the displayed
13/13 downloaded · 13/13 ready summary. Fresh load starts the episode list at
scrollTop 0; all rows through E13 are accessible by scrolling. SSE remains active.
Desktop 2048px has no horizontal overflow.

At 390px, this real page DOES overflow: content grid width 380px reaches x396,
beyond the 390px viewport. The shorter synthetic fixture had passed. Mobile
acceptance is therefore incomplete; fix grid intrinsic sizing and expand the
browser fixture to include realistic metadata/poster content before closing it.
No production changes or media deletions were performed during this review.

### Mobile gap resolved on dev

The stronger fixture includes a poster, long title, metadata, long episode title
and an unbroken release filename. It reproduced horizontal overflow before the
fix. Explicit shrinkable grid tracks, zero minimum widths and text wrapping fix
the layout without hiding overflow. The complete Firefox suite now passes at
320, 390, 768, 1440 and 2048px, as well as live updates/reconnection and persistence.
Read-only Firefox verification of the actual DEV request 17 passes at the same
five widths: 13/13 downloaded and ready, all episode rows accessible, SSE active.
Dev health/database/Shoko checks pass. No schema/data changes or media deletion.
Production unchanged. This resolves the grid overflow recorded above; physical
phone usability and a real active-download pipeline remain separate checks.

## October 17 — library sync and History filters

Current regression suite: **134 passed** in the deployment image, networking
disabled; existing deprecation/async warnings remain (1,245 on this run).
The 23 added cases cover missing IDs/metadata, repeated sync, preservation of
existing values/status, typed IDs, ambiguous/conflicting matches, rollback on
repair failure, admin authorization, History source/user counts, preserved links,
legacy Library Sync bookmarks, empty results and the 100-card display limit.

History now separates Requests / Library imports from actual requesters. Source
is inferred from the existing reserved `Library Sync` requester marker; no schema
migration or historical data rewrite. User filtering is disabled for imports.
State tabs/summary totals describe the selected user/source across all terminal
states; the item count/cards follow the selected state too. Tabs retain filters.

The browser fixture uses the real admin API with synthetic authentication and
mocked media services, only in tests. It verifies one metadata repair, a repeated
sync with zero updates/additions, filters/counts/empty results, and History widths
320/390/768/1440. Narrow cards now shrink to the viewport. Existing detail/SSE
checks remain included. Real Jellyfin scanning is asynchronous: sync reads the
currently indexed library, and a later repeat may be needed after the scan.

Visual review on DEV: open `/history`, select Library imports, switch status tabs,
then choose Requests and a user. Check counts and phone layout. As an admin,
choose Sync Library → Start Sync, inspect results, then Done. A repeat should
report zero updates unless library metadata has changed. Imports show `Source:
Library import` on detail pages. No automatic real-library sync is performed by
the deployment checks; authentication remains required for that action.

Deployment verified: DEV image `status-tracker:library-sync-20261017`. Actual
History shows 11 total / 10 requests / 1 library import, with no overflow at
320/390/768/1440/2048px. Health/database/Shoko connected. No live sync triggered;
production remains unchanged. Backup/rollback are in the infra service README.

### Later DEV data reconciliation

The two 5 Centimeters per Second records were verified as the same physical
movie with conflicting Jellyfin provider IDs. After correction and timeline-
preserving consolidation, expected current totals are **10 total / 10 requests /
0 library imports**. Earlier 11/10/1 counts above describe pre-repair evidence.
Two actual dev syncs returned zero additions/updates/errors; corrected metadata
persisted after library scan completion. Use `/request/2` to review the combined
history and Watch Now link. No playback test was performed.

### Timeline repair label follow-up

136 regressions pass after adding two timeline rendering cases. Library-sync
`Metadata repair` events display “Metadata repaired”; ordinary events still use
state labels, and current request state is unchanged. DEV-only template image
`status-tracker:timeline-label-20261017`; no database changes. Existing warnings
remain (1,259 on this run).

### Import completion visibility

137 regressions pass (existing warnings remain). Radarr/Sonarr Import timeline
entries say Imported even while current state is Matching; ordinary events and
metadata audit labels remain distinct. Tests cover available, downloading and
matching states plus existing movie/TV import handlers. Historical events need
no data rewrite. This records completion, not an observed in-progress import.

### Current real-download evidence

144 regression tests pass after the qBittorrent existing-access compatibility
fix. Actual DEV request 20 reached Downloading with 12 independently measured
episode fractions. Firefox observed 10 swaps in 30 seconds without reload and
passed 320/390/768/1440px. Import/matching/Jellyfin/playback remain pending.
User chose background observation; service/log handoff is in AGENTS.md.
