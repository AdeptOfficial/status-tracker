# qBittorrent already-authorized API access rejected by tracker

Status: fixed on DEV, live download observation in progress.

During the user-requested 12-episode season test (tracker request 20), Sonarr
successfully grabbed the release but the tracker client returned no torrents.
The password-login response was not successful even though a fresh HTTP client
could read `/api/v2/app/version` and `/api/v2/torrents/info` from the app network.
This is server-authorized access; no authentication settings were changed.

The client now probes the version endpoint before attempting password login.
Only HTTP 200 with a version-shaped response is accepted. Protected endpoints
still use username/password login; failed credentials, empty responses and HTML
pages do not authenticate. Raw login response text is no longer logged.

144 regression tests pass, including seven new auth cases. Deployed image
`status-tracker:qbit-auth-20261017`, previous image/source retained. Actual deployed
client authenticates and reads the user's torrent. Tracker reports Downloading,
12 episodes and independently measured file fractions. Full import/matching/
Jellyfin/playback verification is still pending download completion.

Separate infrastructure blocker: qBittorrent user 911 belongs to shared group
1000, but three download directories owned by 1000:1000 were mode 0755. Added
only shared-group write (0775); service-user write probe passed. No recursive
permissions or media deletions. See private infrastructure record for paths.

The user-requested torrent was explicitly started with force-start because the
queue was held behind older errored jobs. Global queue settings and other torrents
were not changed. Restore normal queue behavior on this torrent when validation
finishes. Download is about 28.3 GiB; initial free space about 70 GiB.

## Follow-up: older downloads resumed

The shared-folder permission repair also unblocked older torrents automatically.
Only request 20 was explicitly force-started, but “other jobs unchanged” refers
only to direct commands, not their resulting activity. Three old permission-
error jobs began downloading after the repair; user noticed this in qBittorrent.

Read-only origin investigation: Witch Hat Atelier was added to Sonarr on May 12,
with matching torrent grab timestamps May–August (Sonarr series 48, monitored).
Chainsaw Man: Reze Arc was added to Radarr May 12; current torrent grabbed Sept 20
(Radarr movie 106, monitored). These entries predate this test. All 11 current
Jellyseerr request records were checked; neither title has a surviving request.
Therefore the original person/entry path is not established: do not attribute
it to the user, a specific agent, or production. No unrelated jobs were paused,
unmonitored or deleted during the origin investigation.

User chose background observation and resume on return. Local read-only user
service `status-tracker-dev-request20.service` records summaries every 30s to
`/tmp/status-tracker-20-observation.jsonl`, stops on terminal state or after 24h.
No notification schedule. Full pipeline acceptance still pending; see AGENTS.md.
