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

Older entries: `docs/archive/diary/` (rolled by `tools/diary-roll.py`; read the newest three entries unless investigating history).
