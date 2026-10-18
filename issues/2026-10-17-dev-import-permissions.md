# DEV season import permission failure and speculative tracker progress

Status: import repaired on DEV; downstream matching/Jellyfin/playback pending.

Request 20 (12 episodes) completed its 28.3 GiB download. Sonarr series 51 had
0/12 files and importBlocked queue entries with UnauthorizedAccessException.
Sonarr runs as abc (911:911), supplementary group 1000. Its target parent
`/data/anime/shows` was 1000:1000 mode 0755; the show destination did not exist.

Created only `/data/anime/shows/The Greatest Demon Lord Is Reborn as a Typical Nobody`
with owner 911:1000 and mode 2775. Parent permissions and other shows unchanged.
A temporary hardlink probe as abc passed and was removed. Retried only the
completed season's content path with Sonarr DownloadedEpisodesScan. All 12 episodes
imported; all 12 destination MKVs have link count 2. Free space stayed about 22 GB.
No media deletion, broad library scan, or production change was performed.
Other new show folders may encounter the same parent permission mismatch; this
repair deliberately does not change the whole library ownership or service UID.

The fallback checker had advanced Downloaded to Matching without import evidence.
Removed speculative transitions; confirmed Jellyfin availability recovery remains.
Completed TV episode aggregation now clears speed/ETA even without a new stage.
Eight regression cases bring the isolated suite to 152 passing (1308 warnings).

Before retry, corrected request 20 from Matching to Downloaded only after confirming
Sonarr 0/12 and all tracker episodes Downloaded. Preserved original timeline and
added a tracker State correction audit. Genuine Sonarr import webhooks subsequently
advanced all 12 episodes to Matching. Speed and ETA are now empty.
Removed force-start on the completed test torrent; other jobs were not modified.

DEV image: `status-tracker:import-evidence-20261017`.
Rollback image: `status-tracker:before-import-evidence-20261017`.
Backup: `/opt/backups/status-tracker-import-repair-20261017/` (directory 0700,
SQLite online backup tracker.db and selected source.tar.gz, files 0600).
Do not restore the old database over newer events without reconciling them.
Source sync excluded server secrets and Compose. API keys stayed inside clients.

Follow-up: observe Shoko matching and actual Jellyfin episode readiness, then user
playback. Read-only watcher and paths are in AGENTS.md. Do not repeat force-start
cleanup or rerun the one-time state correction. No production authorization.
