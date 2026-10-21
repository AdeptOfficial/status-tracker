# Status Tracker roadmap (legacy internal planning)

Legacy bundle: internal planning notes moved from `docs/ROADMAP.md` on 2026-10-20.
Not public-safe. Split into one milestone file per item and scrub private details
(hosts, images, handoffs) before anything here feeds the platform page.

Last reviewed: 2026-10-20. DEV validation includes both Cyberpunk season requests;
production deployment and public release require explicit user approval.

## User checkpoint

Further work deferred on2026-10-20. This is a planning handoff, not approval to
continue server work or deploy to production. Read the consolidated private
homeserver handoff `.claude/memory/session-2026-10-20-status-tracker.md` before
resuming; it includes images, rollback, evidence and uncommitted-source warnings.

## Verified on DEV

- Persistent, bounded discovery recovery: confirmed Shoko file matches queue
  refresh jobs; Shokofin memory-cache clearing completes before a library scan.
  No automatic media/VFS deletion; retries survive restart and stop after four
  attempts. Duplicate events do not reset the budget.
- Separate Jellyseerr season requests retain their identities through Sonarr
  correlation. Cards group seasons; detail pages link to independent progress.
- TV readiness verifies playable episodes in the requested season. A show or
  episode notification alone cannot complete the whole season.
- Cyberpunk S1: download → hardlinked import → Shoko matching → automatic
  Jellyfin discovery → 10/10 Ready. All ten video paths readable; user confirmed
  S1E1 playback. S2 also reached10/10 Ready through exact imported Shoko/Jellyfin
  file identities despite separate sequel/S1 numbering in Jellyfin. All ten S2
  VFS videos readable; user playback remains unverified.
- Downloaded/ready counts, measured per-file progress, live updates/reconnection,
  browser-local times and layouts at 320/390/768/1440/2048px are verified.
- Import-complete timeline labels, library-sync ID repair and History filters
  are implemented and DEV reviewed.

Current DEV image: `status-tracker:split-files-20261020`.240 regressions and full
Firefox acceptance pass; real season pages show10/10 Ready and the correct sequel
Watch link. Runtime/source hashes verified. See [testing](TESTING.md), the
[recovery resolution](../bugs/resolved/2026-01-22-anime-matching-no-scan.md),
[season resolution](../bugs/resolved/2026-10-20-separate-season-requests.md),
and `~/git/homeserver/configs/dev/services/status-tracker/README.md` for deployment
and rollback details. Older diary results describe earlier builds.

Movie deletion passed a separate authorized DEV test: file, Radarr record,
Jellyfin item, Jellyseerr request/media and tracker record removed; unrelated
requests preserved. Audit70 is Complete; failed audit69 remains Incomplete.
[Permissions guide](MEDIA-PERMISSIONS.md) and disposable preflight are available.
Fresh Interstellar re-request23/Jellyseerr152/Radarr108 reached Available after
Knaben movie coverage and matching direct Prowlarr/solver egress were restored.
A normal approved4.21GiB release was selected manually for DEV capacity; download,
import and discovery then completed automatically. Actual file hardlinked/readable;
user playback remains unverified for that movie. A subsequent fresh Spider-Man
request24 passed automatic selection through all-service Available, including
actual new-directory modes and writer/reader access without a permission repair.

## Next priorities when the user resumes

1. **Season-safe TV deletion.** Keep the current guard enabled. Implement scoped
   season files/monitoring, explicit whole-show confirmation and Jellyseerr season
   reconciliation without deleting sibling/shared media. Cover failure retention,
   retry/restart, external deletion, active downloads, mixed bulk and anime cleanup
   with isolated tests first; then arrange an intentional user-selected DEV test.
   See [integration gaps](../issues/2026-01-21-deletion-integration-gaps.md).
2. **Regular TV and playback/access coverage.** Test one non-anime request from
   automatic selection through import/Available. Knaben is currently movies-only;
   inspect TV indexer coverage first. Confirm new-movie/S2 playback and phone/proxy
   SSE/reconnect behavior. Multi-season selection within one request is untested.
3. **Production preparation.** With applicable access authorization, verify current
   inventory/versions, actual writer/reader permissions, storage, backup/restore and
   rollback/schema compatibility. Preserve the documented Seerr overlay until an
   official replacement passes its guards/tests. Fresh Spider-Man24 already passed
   unattended/new-folder acceptance for actual DEV roles; shared-group inheritance
   is a separate setup decision, not a completed fleet rollout.
4. **User release decision.** Review evidence and remaining limits. Only explicit
   user approval advances production deployment; publication/status promotion is a
   separate approval after verified production. No automatic announcements.

## Remaining backlog

- [Episode UI follow-ups](../issues/2026-01-22-ui-episode-progress-improvements.md): requested
  grab counts and timeline size presentation need assessment; SEARCHING and
  replacing Matching with Downloaded remain deferred proposals.
- [Unaired episode display](../issues/2026-01-26-pending-episodes-airing-anime.md).
- External deletion detection and service synchronization: reproduce before fixing.
- Proxy-path SSE and physical-device behavior beyond automated viewport checks.
- Existing async/deprecation test warnings.

## Review checklist

- [x] Review the verified recovery, season correlation and UI changes.
- [x] Record automated tests, actual DEV flow and user playback evidence.
- [x] Reconcile resolved issues and preserve unfinished UI requirements.
- [x] Validate S2 imported-file identity across separate sequel numbering.
- [x] Repair and verify DEV Jellyseerr S2 scanner mapping across refresh/rescan.
- [x] Validate one unattended movie and fresh-folder import/permissions.
- [ ] Validate regular-TV flows.
- [x] Verify one regular movie deletion and add operator permission docs to the repo.
- [x] Validate one movie re-request/import with manual approved release selection.
- [ ] Validate remaining user playback/device paths.
- [x] Verify two anime movies through real bulk UI and Shoko cleanup.
- [ ] Implement and validate TV deletion scope and anime TV cleanup.
- [ ] User approval for production deployment and, separately, publication.

Historical commands and January completion claims are superseded by current
[testing instructions](TESTING.md) and infrastructure deployment notes. A plain
Jellyfin library scan is not equivalent to clearing Shokofin's discovery cache.
