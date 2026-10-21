# Status Tracker collapses separate season requests (investigation chronology)

Canonical record: `2026-10-20-separate-season-requests.md`. This file is the full
DEV investigation and repair chronology, moved from the homeserver repo on
2026-10-20 under the one-tracker-per-app rule.

Date: 2026-10-20
Status: Fixed and verified on DEV — S1 Ready10/10, S2 separately Approved

Initial read-only DEV checks found two approved Jellyseerr requests for Cyberpunk:
Edgerunners: request150 for season2 and request151 for season1. Sonarr series52
monitors both seasons. Tracker contains only request21, season2, Approved.
No Cyberpunk torrent or episode rows have appeared yet.

The Jellyseerr webhook handler calls `correlator.find_by_any` with request ID,
TMDB and TVDB IDs. `MEDIA_AUTO_APPROVED` creates a record only when that lookup
returns no existing request. This can reuse the existing show record across
separate season requests. Confirm against isolated webhook reproductions before
changing correlation; downstream Sonarr/episode correlation must also preserve
the correct requested season.

Source: `~/git/homeserver-apps/status-tracker/app/plugins/jellyseerr.py`.
Do not relabel season2 as season1 or replay real requests as test fixtures.

Sonarr's MissingEpisodeSearch commands completed for the two submissions.
No grab is currently visible; the absence of downloads does not establish why
search found no acceptable release, and does not prove a season is unreleased.

Storage check: DEV LXC <media-dev> (`media-dev`) has about21 GiB free on197 GiB root.
All currently listed qBittorrent downloads are complete; no additional queued
Cyberpunk size is known. No cleanup is necessary for the current workload.
User authorizes DEV-only media cleanup if space becomes insufficient. Preserve
the Cyberpunk test content and request20's completed validation season.

## Confirmed and repaired on DEV (later October 20)

The S1 Grab overwrote tracker21's season while retaining S2's Jellyseerr ID150
and requested_seasons=2. Ten S1 episodes were tracked correctly underneath that
mixed identity. Isolated regressions confirmed the cause.

- New TV Jellyseerr IDs now create distinct requests; Sonarr correlation includes
  season and ambiguous show-only matches are rejected.
- TV availability notifications invoke per-episode verification rather than
  declaring the entire requested season available from a single notification.
- Active cards group related seasons; detail pages show both season states and
  links to their independent episode progress/timelines. Firefox verifies the
  deployed home and both detail pages at 320/390/768/1440/2048px with live updates.
- Backed-up transaction preserved tracker21's ten S1 episodes and history, fixed
  its identity to Jellyseerr151, and restored S2 as tracker22/Jellyseerr150,
  Approved. Two audit events explain the historical mixed timeline. Integrity OK.
- Image `status-tracker:seasons-20261020`; backup
  `/opt/backups/status-tracker-before-seasons-20261020`, including identity-before.db.
  183 regression tests passed in the runtime image. Production untouched.

Storage later needed cleanup during the 15.2 GiB download. Removed only DEV
`Cosmic Princess Kaguya! (2026)` after unmonitoring Radarr71; reclaimed12.53 GiB.
Manifest: `/opt/backups/status-tracker-dev-cleanup-20261020/kaguya-removal.json`.
Created Cyberpunk's destination with owner911:1000/mode2775; all ten imported
files verified present and hardlinked (nlink2). About18.2 GiB remains free.

Season1 completed download/import and all ten Shoko matches are confirmed.
Jellyfin discovery remains under investigation: library scans were accepted but
no matching series appeared. Its separate ShokoAutoRefreshMetadata task last ran
in January; a bounded automatic recovery extension is being validated. Do not
claim the full flow passed until actual playable episodes are verified.

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
