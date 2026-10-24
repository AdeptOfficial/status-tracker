## 2026-10-24: Tracker archive layout and standard inbox

`ideas/` folded into `features/` (ideas are Status: Idea); `features/implemented`, `bugs/resolved`,
`issues/resolved` and `ideas/declined` moved to each folder's `archive/`; links and indexes
updated. `inbox.txt` now has `bugs:`, `issues:`, `features:` sections. Rules: `~/git/homeserver-apps/AGENTS.md`.
Next: per-episode fixes first; music support stays Planned.

## 2026-10-24: Music design updated for Soulseek inside Lidarr

[features/2026-10-23-lidarr-music-support.md](features/2026-10-23-lidarr-music-support.md) got an
update section: the homelab retired Soularr, so Soulseek grabs now show in Lidarr's queue and history
like torrents (main signal for both paths); new "import failed, retrying" state (stuck imports are
blocklisted hourly); import-list requests have no requester. Design only, nothing built.

Next: per-episode fixes first; music support stays Planned.

## 2026-10-23: Bug reopened: deletion leaves torrents in qBittorrent

[bugs/2026-01-21-deletion-remove-qbittorrent-torrent.md](bugs/2026-01-21-deletion-remove-qbittorrent-torrent.md)
was resolved by triage on 10-20 because `delete_torrent` exists, but nothing calls it. DEV qBittorrent
had 12 `missingFiles` torrents from earlier deletion tests (removed by hand). Reopened with evidence.

## 2026-10-23: Feature filed: Lidarr (music) support

Owner asked for future Lidarr support after Lidarr was set up on DEV. Filed
[features/2026-10-23-lidarr-music-support.md](features/2026-10-23-lidarr-music-support.md): album as
the request, tracks as items on the per-episode model, requests created from Lidarr events (no
Jellyseerr for music), availability from Navidrome or Jellyfin music. Planned, after the per-episode
fixes. Next: unchanged.

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

Older entries: `docs/archive/diary/` (rolled by `tools/diary-roll.py`; read the newest three entries unless investigating history).
