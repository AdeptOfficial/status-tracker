# Handoff: DEV validation checkpoint, work deferred by the user

Active handoff for status-tracker. Consolidated on 2026-10-20 from the entry point
(`AGENTS.md` handoff and verified-state sections) and the homeserver session memory
file, which now only point here. Consume it, then move it to `docs/archive/`.

## Handoff (from AGENTS.md)

Read `~/git/homeserver/.claude/memory/session-2026-10-20-status-tracker.md` for the
consolidated checkpoint and resume prompt. Do not resume implementation/live work
from this note alone. Next when the user returns: season-safe TV deletion first,
then regular TV, playback/device coverage and production readiness. TV guard stays
on. Production and publication are separately unapproved.

Tracker HEAD5a34941 predates later deployed fixes still in the working tree.
Preserve and review source/tests/docs; do not reset or deploy stale HEAD. Check
actual git status because other projects have concurrent work. No observer needs
restarting: fresh movie24 completed with a verified result.

## Verified DEV state — 2026-10-20 (from AGENTS.md)

- Image `status-tracker:split-files-20261020`;240 regressions pass. Permanent
  Firefox acceptance and actual DEV layouts at 320–2048px pass.
- Cyberpunk S1 tracker21/Jellyseerr151 reached Available 10/10 automatically after
  memory-cache clearing and scanning. All ten video paths readable; user confirmed
  S1E1 playback. S2 tracker22 is Available10/10 after exact imported-file verification across
  split sequel series. Jellyseerr150 is also Available after a guarded DEV Seerr scanner overlay;
  normal refresh/repeat scan passed. See homeserver Jellyseerr guide for rollback.
- Separate season identities, grouped cards and related-season detail links work.
  TV availability requires verified episodes, not just a series directory.
- Durable refresh jobs use confirmed Shoko evidence, bounded retries/backoff and
  cache-task completion before scanning. No automatic VFS/media deletion.
  The metadata-task-only hypothesis failed; do not reinstate that dispatch.
- See `bugs/archive/2026-01-22-anime-matching-no-scan.md` and newest diary for
  evidence. Watcher completed; no observer is required for the finished S1 test.
- TV synchronized deletion is temporarily blocked to prevent whole-show deletion
  from season controls. Failures retain records. Scoped deletion/re-request remains
  open; see newest DIARY and deletion-integration-gaps issue.
- DEV Interstellar movie deletion passed: actual file/library/provider absence
  verified, audit70 Complete; old audit69 remains Incomplete. Fresh re-request23/
  Jellyseerr152/Radarr108 reached Available after Knaben search coverage and direct
  Prowlarr/Byparr egress repair. Approved4.21GiB release selected manually for DEV
  capacity; remaining flow automatic. File readable/hardlinked; user playback
  remains unverified, and that test reused its folder. Later Spider-Man request24 proved automatic
  selection and new-folder import/permissions through all-service Available.
  Read docs/MEDIA-PERMISSIONS.md before deployment or permission work.
- Actual bulk deletion of old anime movies2/4 passed audits71/72, disk/library/
  provider/Shoko absence checks;21.84GiB reclaimed,27.61GiB free. Result banner
  survives refresh with counts/audit link; synthetic success/partial/missing tests pass.
- Spider-Man24: fresh911:911/0755 directory,0644 hardlink, writer probe and
  Jellyfin read/probe passed without chmod or manual selection. All services
  Available; user playback unverified. Free12.80GiB at completion.
- Next work is in the roadmap. Regular-TV flows remain unverified on
  this build. Standalone anime sequels may use different provider numbering.


## Consolidated session checkpoint (from homeserver `.claude/memory/session-2026-10-20-status-tracker.md`)

Date: 2026-10-20
Status: User deferred further work. Documentation/handoff complete; production NOT approved.
Latest live verification: 18:50:54 UTC. This file records observed state, not a new live check.

## Start here when the user resumes

Read root AGENTS.md/CLAUDE.md and inbox.txt, then this file. Application source is
`~/git/homeserver-apps/status-tracker/`; read its AGENTS.md, roadmap/2026-10-20-internal-roadmap-legacy.md,
docs/TESTING.md and issues/2026-01-21-deletion-integration-gaps.md. For server work also read
context/roles/deployer.md, context/core/infrastructure.md and context/core/security.md.
Check git status in every relevant repository and preserve concurrent changes.

Recommended next task: implement season-safe TV deletion, with isolated tests first.
Do not enable the existing TV deletion path: it can target entire shows. User asked
to return to this later; do not resume implementation, downloads, deletions or
server work from this handoff alone. Follow applicable server authorization when
resumed. Production deployment and public status/content promotion remain separately
user-gated. This session's DEV access is not blanket authorization for a new session.

## Current deployed DEV components

DEV Proxmox root@<dev-proxmox>, media LXC <media-dev>, hostname media-dev, IP10.0.2.20.
Operate through `pct exec <media-dev-vmid> -- ...` on the host; verify inventory/hostname first.
No production server was accessed for this work.

| Component | Verified state / ownership |
| --- | --- |
| Status Tracker | `status-tracker:split-files-20261020`, port8100. Source/Compose `/opt/status-tracker`; config/data `/opt/appdata/status-tracker`. |
| Media stack | Live Compose `/opt/stacks/docker-compose.yml`, project `stacks`. Canonical repo backup `configs/dev/stacks/media/docker-compose.yml`. |
| Seerr, container named jellyseerr | Seerr3.5.0 with `seerr-dev:anidb-season-20261020`, port5055. App-owned overlay in `~/git/homeserver-apps/seerr-dev-patches/`, local commit203a69c, no remote/push. |
| Prowlarr | Knaben id10, movies tag only, tested/synced to Radarr. Free public NoAuth provider; no provider account/key.1337x test repaired. |
| Search routing | Prowlarr and internal-only byparr-direct share direct egress. Original VPN-side Byparr remains for Jackett. |
| Download routing | qBittorrent shares Gluetun namespace; VPN exit and OUTPUT DROP verified. Existing VPN containers were preserved. |

## Completed real flow and deletion checks

| Tracker / request | Result |
| --- | --- |
|21 / Jellyseerr151, Cyberpunk S1 | Available10/10. All files readable; user confirmed S1E1 playback. |
|22 / Jellyseerr150, Cyberpunk S2 | Available10/10. Sonarr S2 maps to separate Jellyfin Edgerunners II/S1 via exact imported Shoko file identity. Watch link targets actual sequel. All ten readable; user playback unverified. |
|23 / Jellyseerr152 / Radarr108, Interstellar | Available across services. Manual normal selection of an approved4.21GiB result due storage; remaining flow automatic. Existing folder reused. |
|24 / Jellyseerr153 / Radarr109, Amazing Spider-Man2 | Fully automatic selection → download → fresh-folder import → Available across tracker/Jellyfin/Jellyseerr. No manual scan/status/permission fix. User playback unverified. |
| Old Interstellar19 | Original audit69 falsely completed; corrected to Incomplete. Verified retry audit70 Complete after scoped permission repair; actual file/library/provider absence checked. |
| Old movies2 and4 | User bulk-deleted 5 Centimeters per Second and Garden of Words. Audits71/72 Complete; actual file, Radarr, Jellyfin, Jellyseerr and Shoko absence verified.21.84GiB reclaimed. |

Bulk success UX now retains an accessible count banner after refresh, with audit
link/dismissal and accurate partial/omitted/empty-result warnings. Synthetic browser
coverage passes. TV single/bulk/external synchronized deletion remains BLOCKED.

Fresh Spider-Man target folder was absent before import. Radarr created it at
18:48:22 UTC as911:911/0755; file911:911/0644,15467520894bytes, hardlink count2.
Actual Radarr UID/GID911, groups911/1000, umask0022. Disposable create/rename/delete
probe as911:1000 passed and cleaned up. Jellyfin read and ffprobe passed. Tracker
Verified event18:50:38.753437 UTC; all-service observer result verified18:50:54.
This proves access for actual writer/reader roles, NOT arbitrary cross-UID group
write or a fleet2775/umask002 rollout. Do not recommend per-request mkdir/chmod.
Latest free space12.80GiB; recheck before another download. Preserve test requests
20–24 and their media unless the user intentionally selects a later deletion test.

## Fixes, tests and limits

-240 isolated Status Tracker regressions pass; full Firefox suite and real DEV
  pages/SSE/320/390/768/1440/2048px layouts pass. Later fresh-movie observation/docs
  did not change runtime code or rerun the whole suite. Existing warnings remain.
- Discovery recovery is durable/bounded, confirmed Shoko file evidence only,
  memory-cache clear completion BEFORE scan. Do not reinstate the failed
  metadata-task-only hypothesis, reset budgets, or delete VFS/media for discovery.
- Split-sequel verification uses imported path → confirmed Shoko File → playable
  Jellyfin episode, rejecting missing/ambiguous/shared evidence and stale Ready
  flags. Duplicate/shared multi-episode source files need separate handling.
- Seerr scanner originally ignored AniDB season mapping after parent TMDB/TVDB
  resolution. Overlay applies mapping only to single-S1 layouts with the same
  mapped show and an existing target season; conflicts skip. Ten tests pass
  against compiled runtime, original regression fails. No full-project semantic
  typecheck claimed. Source-hash guard rejects unreviewed upstream upgrades.
- Supported Seerr scan POST `/api/v1/settings/jobs/jellyfin-full-scan/run`. Normal
  scan fulfilled S2; targeted Jellyfin metadata refresh and repeat scan passed.
  Full scan also corrected Bocchi availability:12 readable S1 videos; empty future
  S2 stayed unavailable. Other media identities/statuses preserved.
- Jellyfin `/Items/{id}` GET can return400 here. Use the supported `/Items`
  collection query;400 is not proof of absence. Never turn API errors into success.

## Next production gates, in agreed order

1. Season-safe TV deletion: preflight the entire selection; remove only selected
   season files; preserve sibling files/monitoring; reconcile Jellyseerr without
   deleting shared show media. Distinguish explicit whole-show deletion and add
   confirmation. Cover failure/retry/restart/external deletion, active downloads,
   mixed bulk requests and anime cleanup. Keep guard until synthetic acceptance
   passes, then plan an intentional user-selected DEV test. Do not use current
   valuable test files as synthetic fixtures or bypass admin authentication.
2. One regular non-anime TV request/import/availability test; inspect indexer
   coverage first (Knaben rollout was movies-only). Monitor normal selection.
3. User playback of the new movie/S2; phone/proxy access, SSE/reconnect and physical
   devices. Automated widths/file probes are not actual device playback proof.
4. Production readiness: verify current inventory/versions, actual service
   permissions, capacity, stopped-service backup/restore and rollback compatibility.
   Account for nullable deletion retry-path migration and separated season rows.
   Document/preserve the Seerr overlay or verify an official replacement before
   removing it. No production inspection/deployment authorization is implied.
5. Review evidence with user, obtain explicit production deployment approval;
   publish/status promotion requires separate user approval after verified prod.

Other backlog: multi-season selection in ONE request, requested grab-count/timeline
size UX, unaired episodes, inherited test warnings. See existing issue files;
do not claim every historical UI proposal is complete.

## Private rollback/evidence locations (DEV LXC <media-dev>)

- Tracker current: `/opt/backups/status-tracker-before-split-files-20261020/`,
  image `status-tracker:before-split-files-20261020`.
- Earlier verified deletion: `/opt/backups/status-tracker-before-verified-delete-20261020/`;
  scoped deletion retry evidence under `/opt/backups/status-tracker-interstellar-delete-20261020/retry/`.
- Bulk UI: `/opt/backups/status-tracker-before-bulk-feedback-retry-20261020/`.
- Seerr: `/opt/backups/seerr-before-anidb-season-20261020/`,
  image `seerr-dev:before-anidb-season-20261020`.
- Search: `/opt/backups/prowlarr-knaben-direct-20261020/`.
- Fresh movie observer: `/opt/backups/status-tracker-fresh-spiderman-20261020/`;
  result.json is VERIFIED; observer completed. No restart needed. Contains private
  selected evidence/scripts, not a recurring monitor service.

Backups may contain private settings: never dump/copy into repos. Retain current DB
on ordinary image rollback; do not replace later activity with an old full DB.
Do not roll back to pre-season code against separated season rows.
No credentials were exposed. Limited prior Prowlarr key use was explicitly approved
for server-side handling only; that is not general permission to read secret files.
Use existing configured clients internally without logging values. UI auth stays
user-owned; no fabricated admin identities or token/session harvesting.

## Repository evidence and worktree state

- `notes/2026-10-20-dev-fresh-folder-movie.json` — final automatic fresh-folder proof.
- `notes/2026-10-20-dev-seerr-season-mapping-fix.json` — scanner proof/limits.
- `notes/2026-10-20-dev-split-sequel-validation.json` — tracker file-identity proof.
- `notes/2026-10-20-dev-bulk-delete.json` and
  `notes/2026-10-20-status-tracker-deletion-retry.json` — real deletion proof.
- `notes/2026-10-20-dev-knaben-validation.json` — search/VPN routing proof.
- Service guides: `configs/dev/services/status-tracker/README.md`,
  `configs/dev/services/jellyseerr/README.md`, `configs/dev/services/prowlarr/README.md`.
- Tracker `docs/MEDIA-PERMISSIONS.md`, disposable preflight script, docs/TESTING.md,
  resolved split-season issues and open issues/2026-01-21-deletion-integration-gaps.md.

Tracker HEAD was5a34941 at handoff, with later deployed source/tests/docs still
UNCOMMITTED in its worktree. Do not reset it or redeploy HEAD as if it were current.
Seerr overlay is locally committed203a69c. Homeserver has concurrent other-project
work; inspect actual git status, do not stage all or push unrelated changes.
Public release/source publication has not been authorized.

Existing deferred content candidate: studio/docs/content-backlog.md,
`2026-10-17-status-tracker-episode-progress`. Updated with facts; no article/public
status change approved. Resume existing candidate only if user requests it.

## Resume prompt

Continue Status Tracker from
`.claude/memory/session-2026-10-20-status-tracker.md`. User deferred work; when they
resume, start with the season-safe TV deletion design/tests while preserving the
TV guard and current DEV evidence. Read app AGENTS/ROADMAP/TESTING and open deletion
issue. Movie flow, new-folder permissions, bulk movies and both anime seasons have
passed their documented DEV checks. Production and publication remain user-gated.
