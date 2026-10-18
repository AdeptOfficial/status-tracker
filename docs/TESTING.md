# Status Tracker testing

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
