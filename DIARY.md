## 2026-10-23: DEV writers aligned with production; episode list layout bug filed

Gotham imports were blocked: Sonarr ran as 911 (live DEV Compose had lost PUID/PGID) and could not
create its folder in a 755 `tv/shows`. DEV now runs qBittorrent, Prowlarr, Jackett, Sonarr and Radarr
as 1000 like production, with 775 show roots; imports resumed on their own (infrastructure record in
the homeserver repo). `docs/MEDIA-PERMISSIONS.md` notes the 911 identity was unintended. Filed
[episode list status text wraps and clips](bugs/2026-10-23-episode-list-status-text-wraps-and-clips.md)
from the owner's screenshot (no solution yet). Next: follow Gotham to Available.

## 2026-10-23: Per-episode feature rewritten with the agreed goal

`features/2026-01-18-status-dashboard-multi-episode-tracking.md` renamed to
[per-episode-progress-and-request-state](features/2026-01-18-per-episode-progress-and-request-state.md)
and rewritten: goal agreed with the owner (one bar per episode; request DOWNLOADING until every episode
is downloaded; Searching/Not found rows; per-episode Stalled), DEV Gotham and production anime evidence,
and solution A–E against the current code. Original January spec and the 10-17 scope kept under
History. Both 10-23 bugs link to it; January plan points to it. Docs only. Next: Gotham's import phase
(per-episode availability), then implementation when the owner says so.

## 2026-10-23: Bug filed: TV request stops tracking after the first episode

Same DEV Gotham S5 test: when 1 of 12 episodes finished, the request went DOWNLOADED and the
qBittorrent poll (GRABBING/DOWNLOADING requests only) dropped it; at 18:41 qBittorrent had 2/12 done
and 73%, the tracker still 1/12 at 8% with no speed. Filed
[bugs/2026-10-23-tv-poll-stops-after-first-episode.md](bugs/2026-10-23-tv-poll-stops-after-first-episode.md)
with a proposed fix; not implemented. Next: watch the remaining episodes through Sonarr import.

## 2026-10-23: Bug filed: episode progress unknown for space-named files

DEV regular-TV test (Gotham S5, Knaben via Prowlarr, one torrent per episode): episodes showed
"progress unknown" while qBittorrent had per-file progress. The multi-episode guard in
`file_progress()` reads ` 1080p` after `S05E02` as a second episode. Filed
[bugs/2026-10-23-episode-progress-unknown-space-named-files.md](bugs/2026-10-23-episode-progress-unknown-space-named-files.md)
with a proposed pattern and tests; not implemented. Also seen: APPROVED requests never time out
(the state machine has no APPROVED → TIMEOUT), not filed yet. Next: unchanged; finish following
the TV test to Available.

## 2026-10-21: Split-anime verification committed on release

The split-file anime availability work (Jellyfin client and verifier, history
view, permissions guide, tests) had stayed uncommitted after the 2026-10-20
session. Docker suite 240/240, then committed as `50efeaa` on `release`
through a feature branch; this matches the `split-files-20261020` image on
DEV. Diary rolled. Next: unchanged, see the consolidated handoff below.

## 2026-10-20: README trimmed to overview, status, run and links

Project structure, network requirements and webhook configuration moved to
`docs/SETUP.md`; API notes to `docs/API.md`; troubleshooting to
`docs/TROUBLESHOOTING.md`. README is now 70-odd lines; docs index updated and its
tracker wording matches the current layout. No source change.

## 2026-10-20: Handoff scrubbed for the public repo

The consolidated handoff was copied from a private file and carried private
addresses and LXC ids for one pushed commit; replaced with the usual placeholders.
Real values stay in the homeserver service README. No credentials were involved.

## 2026-10-20: Session state moved out of the entry point

`AGENTS.md` is pointers and working rules only. Its handoff and verified-DEV-state
sections, plus the homeserver session memory checkpoint, are consolidated in
`handoffs/2026-10-20-dev-validation-checkpoint.md` (the active handoff; move it to
`docs/archive/` once consumed). The January `CONTEXT-RESUME.md` was stale and is
archived. No source or runtime change.
Next: season-safe TV deletion with isolated tests first (see the handoff); then the
ten open bugs' DEV checks listed in their triage notes.

## 2026-10-20: Bug triage from repo evidence; ops runbook complete

First pass of `~/git/workflows/triage.md` over the 30 open bugs, using resolved
records, the Oct 20 verified-flow diary entries and the current code, with no live
check. 20 closed: 17 resolved by later work (per-file Jellyfin verification, SSE and
live updates, automatic import and permissions, counters and progress, the
downloading→matching transition, qBittorrent deletion client, alternate-title
matching), 2 superseded (`SYNCING_LIBRARY` removed; library-sync IDs covered by a
resolved record), 1 not reproducible. 10 stay open with a note saying what would
verify each on DEV: Radarr re-request, queue desync and anime filenames, the
`downloaded` timeline entry, one legacy bundle, and five UI checks on the rebuilt
build. Every record carries a dated Triage section; originals untouched.
Next: verify the ten open items on DEV when a session has server access.

## 2026-10-20: Public-repo scrub

This repo is public on GitHub. Replaced private IPs, LXC ids and internal
hostnames with placeholders (`<dev-proxmox>`, `<media-dev>`, `<prod-media>`) across
docs, records, archives and memory files; real values stay in the private homeserver
service README. Removed `app/services/shokofin_vfs.py` (dead code with a hardcoded
SSH target; nothing imported it) and moved `scripts/deploy.sh` to `ops/deploy-dev.sh`,
which now requires `PROXMOX_HOST` and `LXC_ID` from the environment. gitleaks
(history and working tree) found only `YOUR_API_KEY` placeholders, recorded in
`.gitleaksignore`; a pre-commit hook now blocks staged secrets. Tests not rerun:
the deletion touched no imported module. Nothing deployed.

## 2026-10-20: Database section in the ops runbook

Added engine, data path, backup, integrity, restore-check and migration rows to
`ops/README.md`, linked to `~/git/workflows/database-change.md` and the new
`deploy-to-dev.md`. Documentation only.

## 2026-10-20: ops/README.md runbook added

Portable runbook built from `docker-compose.yml`, `Dockerfile`, `.env.template`, the
homeserver deploy script and the homeserver service README: runtime shape, run
anywhere, tests before deploy, DEV deploy via `~/git/homeserver/scripts/deploy-status-tracker.sh`
(kept there because it embeds homelab hosts), production on hold behind the
promotion gate, the backup/rollback pattern used for every DEV release, verify
steps and data locations. No source or runtime change; nothing deployed.

## 2026-10-20: ideas/ and roadmap/ added to the standard layout

Added `ideas/` (feature entry stage; accepted → `features/`, declined →
`ideas/declined/`) and `roadmap/` (public-safe milestones that feed the AdepT
platform and studio pages; `roadmap/shipped/` when released). Indexes generated by
`~/git/homeserver-apps/tools/tracker-index.py`; empty lifecycle folders hold a
`.gitkeep`. `docs/ROADMAP.md` moved to `roadmap/2026-10-20-internal-roadmap-legacy.md` as a legacy bundle (not public-safe; split and scrub before publishing); links in README, docs/README, CONTEXT-RESUME, AGENTS.md, one issue and the homeserver session memory updated. No source or runtime change.

## 2026-10-20: Records renamed with creation dates; indexes now tool-generated

Every undated record in `bugs/`, `issues/` and `features/` was renamed to
`YYYY-MM-DD-slug.md` using its own Created/Date field (34 files). Links in
CONTEXT-RESUME.md, docs/ROADMAP.md, docs/handoff-qbit-deletion.md, sibling records
and the homeserver repo were updated; `docs/archive/` and diaries keep old names as
history. Index READMEs are now generated by `~/git/homeserver-apps/tools/tracker-index.py`
and must not be hand-edited; four legacy bundles carry a marker line. `CLAUDE.md`
points to the shared rules in `~/git/homeserver-apps/AGENTS.md`. No source change.

## 2026-10-20: Tracker reclassified into bugs/, issues/, features/

Every record was classified by the global definitions and moved: 30 malfunctions
to `bugs/` (10 resolved under `bugs/resolved/`), gaps/UX/integration/investigation
records stay in `issues/` (6 resolved), and eight feature-shaped records
(path-matching fallback, Japanese titles, per-episode tracking, bulk sync, dynamic
Jellyfin URL, existing-media detection, external-deletion detection, implemented
SYNCING_LIBRARY state) moved to `features/`. Merged duplicate pairs: poster missing
→ `bugs/2026-01-25-poster-not-loading.md`; qBittorrent deletion →
`bugs/deletion-remove-qbittorrent-torrent.md`; Radarr auto-import →
`bugs/radarr-auto-import-not-working.md` (old `issues/bugs/` subfolder removed).
Added `features/implemented/` (SYNCING_LIBRARY state moved there); the library-sync
metadata request moved from `issues/resolved/` back to open `features/` because it
recorded no resolution.
Four legacy bundled records remain whole and are flagged in the indexes:
`bugs/2026-01-22-monitoring-session-bugs.md`, `issues/2026-01-22-ux-improvements.md`,
`issues/2026-01-25-timeline-ux-improvements.md`, `issues/testing-jellyfin-verification-flow.md`.
Links in AGENTS.md, CLAUDE.md, CONTEXT-RESUME.md, docs/ROADMAP.md and
docs/handoff-qbit-deletion.md updated; archived session notes left as history.
No source or runtime change.

## 2026-10-20: Homeserver-filed bugs moved here; tracker indexes added

Under the one-tracker-per-app rule (`~/git/AGENTS.md`), three bug records moved
from `homeserver/issues/bugs/` into `issues/`: `2026-01-24-tmdb-id-mismatch-fallback`
(open; links the 2026-10-17 provider-mismatch repair, verifier fallback unconfirmed),
`resolved/2026-10-20-separate-season-requests-chronology` (full DEV chronology
beside the canonical resolved record), and the 2026-01-24 UI-bugs bundle split into
`deleted-items-remain-until-refresh`, `grabbed-badge-alignment` and
`matching-state-shows-error-color`, with its SSE and 0 B size reports merged into
the existing 2026-01-25 records. All three carry "unverified against the current
build". Added index-only `issues/README.md` and `features/README.md`; `CLAUDE.md`
inbox step now says one new file per item. No source or runtime change.

## 2026-10-20: Status Tracker consolidated handoff; user deferred further work

Added .claude/memory/session-2026-10-20-status-tracker.md with final DEV evidence,
240 tracker/10 scanner test distinctions, IDs,12.80GiB storage, permission limits,
completed observer, source/worktree cautions, private rollback and release gates.
Linked from domain/service/app entry points; roadmap order now matches agreed
next call: season-safe TV deletion first, then regular TV, playback/device checks
and production readiness. Current TV guard remains; no production/publication
approval. Later tracker fixes remain uncommitted beyond5a34941; overlay203a69c
local only. Preserve concurrent work and do not deploy stale HEAD. Documentation
only: no new server access, tests, deployment, deletion, download or public content.

## 2026-10-20: Fresh automatic movie/folder flow passed on DEV

Amazing Spider-Man2 tracker24/Jellyseerr153/Radarr109 completed the unattended
request test: auto-grab17:19:26, download18:47:08, import18:48:22, all-service
Available observed18:50:54 UTC. Folder was confirmed absent before import, then
created18:48:22 by Radarr911:911 with0755; hardlinked file15467520894bytes,0644,
nlink2. Actual Radarr groups911/1000 and umask0022. Disposable create/rename/delete
probe as911:1000 passed and cleaned up; Jellyfin read and ffprobe passed (8494.771s).
Ready page, correct Watch link, SSE and five viewport widths passed. No manual
release selection, scan/status write, mkdir/chmod repair or media deletion.

Observer completed verified result under private
/opt/backups/status-tracker-fresh-spiderman-20261020/. DEV free12.80GiB. Evidence
notes/2026-10-20-dev-fresh-folder-movie.json. This proves required writer/reader
access for these actual service identities, not group-write access for every
other UID: new directories are911:911/0755, not a fleet2775/umask002 rollout.
User playback remains unverified. App/scanner code and images unchanged; no new
regression run needed for observation/docs. Updated permissions guide, roadmap,
service notes and existing deferred content candidate. Next release work: regular
TV coverage, season-safe TV deletion and device/playback checks. Production untouched.

## 2026-10-20: Fresh automatic movie/folder validation running on DEV

User requested The Amazing Spider-Man2: tracker24/Jellyseerr153/Radarr109/TMDB102382.
Auto-approved17:19:12 UTC; Radarr grabbed at17:19:26; qBittorrent started17:19:37.
No manual selection, profile override or permissions changes. Selected14.41GiB
release fits DEV storage. Confirmed target movie folder absent before import,
so this tests real creation rather than reuse. Actual Radarr UID/GID911, groups
911/1000, umask0022. Live movie detail/SSE/five viewport checks pass.

User does not need to create folders or change permissions. A bounded independent
DEV observer at /opt/backups/status-tracker-fresh-spiderman-20261020/ polls every20s
(max540 checks), records progress and, after import, verifies fresh folder/file
modes, hardlinks, actual Jellyfin read/probe and disposable writer operations.
It waits for tracker and Jellyseerr Available before writing a verified result.
No live config/status/scan mutation or media deletion. Root-only reports include
progress.json, file-verification.json, result.json; check them on follow-up.
Latest17:26:27 UTC:16.97% downloading,25.02GiB free. Import/permissions/availability
remain PENDING; do not mark roadmap passed from setup alone. Evidence:
notes/2026-10-20-dev-fresh-folder-movie.json. Production untouched.

## 2026-10-20: DEV Jellyseerr split-sequel availability repaired and verified

Created app-owned `~/git/homeserver-apps/seerr-dev-patches/` with upstream scanner
source/license, guarded TS/compiled overlay, build tools and isolated integration
tests. DEV Seerr3.5.0 now applies AniDB season mapping for a single numbered S1
only after mapped TVDB identity resolves to the same show and target season exists.
Native multi-season/S2 and movies retain normal handling; conflicting mappings skip.
Original regression reproduced;10 tests pass against the exact compiled artifact,
network disabled/disposable DB. No full-project semantic typecheck claim. Final
image changes only scanner TS/JS, no runtime dependencies or schema changes.

Deployed only jellyseerr via canonical/live media Compose image
`seerr-dev:anidb-season-20261020`. Drift guards, stopped-service private backup,
quiet Compose validation and startup verification pass; all other container IDs
unchanged. Supported full scan fulfilled request150 within6sec; both Cyberpunk
seasons and Interstellar now Available. Targeted Jellyfin metadata refresh204 and
repeat full scan passed; ten sequel VFS files readable. No manual status/DB edits,
provider-ID edits or locks. Media identities preserved. Full scan also corrected
Bocchi4→5: all12 S1 videos readable, empty future S2 remains unavailable; all other
media statuses unchanged. Free27.44GiB after temporary archive cleanup. No media
removed. Private rollback /opt/backups/seerr-before-anidb-season-20261020/ and
image seerr-dev:before-anidb-season-20261020 retained. Do not restore old DB over
later activity. Production untouched; no upstream submission/public release.

Updated Jellyseerr guide, existing issue, tracker roadmap/history and deferred
content candidate. Evidence notes/2026-10-20-dev-seerr-season-mapping-fix.json.
Next release gates: unattended request into fresh folder/creation permissions,
regular TV and season-safe TV deletion. Overlay needs review on upstream upgrade.

## 2026-10-20: DEV split-sequel tracker fix verified; Jellyseerr scanner gap diagnosed

Interstellar request152 synchronized normally to Available at16:30:08 UTC; no
repair required. S2's ten imports were already in Jellyfin as separate Edgerunners
II / Season1, while tracker22 checked original show / Season2 and exhausted its
bounded discovery retries. Added exact imported-path→confirmed Shoko File→Jellyfin
episode verification across split series. Reject missing/ambiguous/shared files,
wrong series and stale readiness. Source IDs345–354 independently match ten
readable VFS videos. DEV `status-tracker:split-files-20261020` reached Available
10/10 automatically at16:50:36.520 UTC; actual sequel Watch link and S1 preserved.
No manual scan/status write/retry reset.240 regressions and full Firefox suite
pass; both live season pages/SSE/320–2048px layouts pass. Runtime source hashes
verified. No dependency/schema changes. Private stopped-app backup
/opt/backups/status-tracker-before-split-files-20261020/; rollback
status-tracker:before-split-files-20261020. Do not restore old DB over later events.

Jellyseerr3.5.0 request150/season2 remains unavailable: installed scanner only uses
AniDB season mapping after TMDB/TVDB resolution fails. Duplicate parent IDs resolve
the original show first, bypassing cached AniDB19445→TVDB384541 season2 mapping.
Opened issues/bugs/dev-jellyseerr-split-anime-season-availability.md with durable
repair/acceptance plan; no third-party scanner, metadata or availability mutation.
Evidence notes/2026-10-20-dev-split-sequel-validation.json. Next: scanner mapping,
fresh-folder/unattended request test and season-safe TV deletion. Production and
public release untouched; existing deferred content candidate updated only.

## 2026-10-20: DEV bulk movie deletion verified and feedback repaired

User deleted old requests2 (5 Centimeters per Second) and4 (The Garden of Words)
through authenticated bulk UI. Audits71/72 Complete. Independent checks confirm
real files absent, both Radarr IDs404, no matching Jellyfin items, Jellyseerr
requests404/media absent, Shoko file queries0 results, tracker rows removed.
All unselected identities preserved; protected file counts Interstellar1,
Cyberpunk20 and Demon Lord12. Recovered21.84GiB; DEV free27.61GiB. Anime movie
cleanup now has two real passes; TV deletion remains blocked and unverified.

User found success feedback vanished on refresh. DEV now runs UI-only image
`status-tracker:bulk-feedback-20261020` on unchanged verified-delete backend.
Accessible result banner survives refresh, reports selected/completed counts,
links audits, supports dismissal, warns for partial/omitted/empty responses.
Full Firefox acceptance passes these outcomes, reload and mobile widths using
synthetic responses (no further real deletions). Original backend226-test baseline
unchanged; not rerun for this template-only patch. Runtime/source hash and DEV
served markup/health verified. First deploy smoke wrongly expected admin JS in
an anonymous response; automatic rollback worked before corrected smoke/redeploy.
Private backup /opt/backups/status-tracker-before-bulk-feedback-retry-20261020/;
rollback image status-tracker:before-bulk-feedback-retry-20261020. No DB restore,
credentials exposed, production changes or public announcement. Evidence:
homeserver notes/2026-10-20-dev-bulk-delete.json. Existing content candidate updated.

## 2026-10-20: DEV bulk UI deletion test prepared, not yet executed

User offered to exercise mass deletion. Selected old movie requests2 (5 Centimeters
per Second) and4 (The Garden of Words),21.84GiB actual files/nlink1. Both previews
allow Radarr/Shoko/Jellyfin/Jellyseerr sync. Preserving20/21/22/23 and all TV.
Scoped0755→0775 repair on anime/movies parent plus these two directories; owners
unchanged. Owner-only DB/request/permission before-snapshot under
/opt/backups/status-tracker-bulk-delete-20261020/ in DEV media LXC <media-dev>. User will
click the actual bulk action in their authenticated browser; no admin credential
collected or auth bypass. No media deleted yet. Verify audit/file/library/provider
absence, Shoko cleanup, space recovery and protected files after click. Evidence:
homeserver notes/2026-10-20-dev-bulk-delete.json. Production unchanged.

## 2026-10-20: DEV movie re-request flow verified after indexer repair

Knaben id10 added/tested on DEV, movies tag only; Radarr returned68 results with33
approved. Prowlarr now uses internal-only byparr-direct with matching direct
egress. Full1337x test passed/backoff cleared; qBittorrent remains on Gluetun VPN
with OUTPUT DROP, existing containers unchanged. Existing Prowlarr key used only
internally under explicit user authorization; no key or public IP displayed.
Private rollback retained; infrastructure Compose/service guide updated.

Interstellar tracker23/Jellyseerr152/Radarr108: selected a normal approved4.21GiB
1080p release because preferred33.26GiB remux exceeded DEV capacity. This proves
manual approved selection followed by automatic download/import/discovery, not
fully unattended release selection. No profile/rejection override, manual scan or
direct status update. Download complete16:24:20 UTC, import16:25:18, then Available.
Actual file4515260620bytes, nlink2, UID911:GID911,0644, reused directory0775;
read inside Jellyfin and ffprobe HEVC/audio duration10144.256sec passed. Free5.59GiB,
no cleanup needed. User playback and fresh-directory creation remain unverified.
Jellyseerr still reported media status3 at the final check; its availability-cache
refresh is pending, so this does not prove every service cache is synchronized.
Live Firefox movie detail, SSE and320/390/768/1440/2048px layouts passed. App image
unchanged (`status-tracker:verified-delete-20261020`); previous226 runtime tests
remain the code baseline. TV scope, anime cleanup and regular TV remain open.
Evidence: homeserver notes/2026-10-20-dev-knaben-validation.json. Production and
public release untouched; deferred content candidate updated without publishing.

Older entries: `docs/archive/diary/` (rolled by `tools/diary-roll.py`; read the newest three entries unless investigating history).
