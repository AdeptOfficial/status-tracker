# Status Tracker roadmap

Last reviewed: 2026-10-20. DEV validation is complete for Cyberpunk Season 1;
production deployment and public release require explicit user approval.

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
  S1E1 playback. S2 remains separately approved, awaiting download.
- Downloaded/ready counts, measured per-file progress, live updates/reconnection,
  browser-local times and layouts at 320/390/768/1440/2048px are verified.
- Import-complete timeline labels, library-sync ID repair and History filters
  are implemented and DEV reviewed.

Current DEV image: `status-tracker:verified-delete-20261020`. **226 regression tests pass**
in the runtime image; Firefox acceptance passes. See [testing](TESTING.md), the
[recovery resolution](../issues/resolved/2026-01-22-anime-matching-no-scan.md),
[season resolution](../issues/resolved/2026-10-20-separate-season-requests.md),
and `~/git/homeserver/configs/dev/services/status-tracker/README.md` for deployment
and rollback details. Older diary results describe earlier builds.

Movie deletion passed a separate authorized DEV test: file, Radarr record,
Jellyfin item, Jellyseerr request/media and tracker record removed; unrelated
requests preserved. Audit70 is Complete; failed audit69 remains Incomplete.
[Permissions guide](MEDIA-PERMISSIONS.md) and disposable preflight are available.
A new request/download cycle has not been submitted.

## Next priorities

1. Observe S2's eventual DEV download/import. Verify provider episode identities,
   especially if Shoko/Jellyfin represents the sequel as a separate Season 1.
   Multi-season selection within one Jellyseerr request is not established by
   the two separate request IDs tested here.
2. Complete [deletion/re-request integration gaps](../issues/deletion-integration-gaps.md)
   after the interim DEV safety patch. TV deletion is blocked because existing
   APIs delete whole shows. Implement scoped deletion, explicit whole-show
   confirmation and season availability reconciliation before re-enabling it.
   Failure retention and one regular movie deletion pass; fresh re-request and
   anime cleanup remain unverified. Before release, test fresh-import creation
   modes against the documented group/umask policy; the DEV repair changed only
   two directory modes, not fleet configuration.
3. Validate a regular movie and regular TV request on the current build. Check
   indexer availability first; the January blocker has not been reverified.
4. Review release readiness with the user after the remaining coverage gaps.
   Do not deploy to production or advance public site status automatically.

## Remaining backlog

- [Episode UI follow-ups](../issues/ui-episode-progress-improvements.md): requested
  grab counts and timeline size presentation need assessment; SEARCHING and
  replacing Matching with Downloaded remain deferred proposals.
- [Unaired episode display](../issues/pending-episodes-airing-anime.md).
- External deletion detection and service synchronization: reproduce before fixing.
- Proxy-path SSE and physical-device behavior beyond automated viewport checks.
- Existing async/deprecation test warnings.

## Review checklist

- [x] Review the verified recovery, season correlation and UI changes.
- [x] Record automated tests, actual DEV flow and user playback evidence.
- [x] Reconcile resolved issues and preserve unfinished UI requirements.
- [ ] Validate S2 import/provider numbering and regular-media flows.
- [x] Verify one regular movie deletion and add operator permission docs to the repo.
- [ ] Validate intentional re-request/import and fresh-folder creation modes.
- [ ] Implement and validate TV deletion scope and anime cleanup.
- [ ] User approval for production deployment and, separately, publication.

Historical commands and January completion claims are superseded by current
[testing instructions](TESTING.md) and infrastructure deployment notes. A plain
Jellyfin library scan is not equivalent to clearing Shokofin's discovery cache.
