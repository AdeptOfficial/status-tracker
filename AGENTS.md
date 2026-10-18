# Status Tracker agent entry point

Read `CLAUDE.md`, `inbox.txt`, newest `DIARY.md`, `docs/ROADMAP.md` and git status.
Global `~/git/AGENTS.md` applies. Preserve unrelated work.

Current stack: FastAPI, SQLite, Jinja, HTMX and SSE. No stack migration planned.
Testing instructions: `docs/TESTING.md`. Extend the existing regression suite and
permanent browser suite; never use real media downloads/deletions as fixtures.

October 17 episode progress is deployed to DEV only. User explicitly said to stay
in dev and not push to production. Git commits/pushes do not authorize deployment.
Real pipeline validation is active: DEV request 20, 12 episodes. User chose to
leave a read-only watcher running and resume checks on return. Local user service
`status-tracker-dev-request20.service` polls every 30s for up to 24h, stops on
available/failed/timeout. Verify service and log freshness before relying on it.
Observations: `/tmp/status-tracker-20-observation.jsonl`; script and PID files:
`/tmp/watch-status-tracker-20.py`, `/tmp/status-tracker-20-watcher.pid`.
Request 20 download and Sonarr import are complete (12/12 hardlinked); force-start
has been removed. Shoko processing observed. Pending: matching/Jellyfin readiness
and user playback. Import repair and 152-test DEV release are recorded in
`issues/2026-10-17-dev-import-permissions.md`. Do not rerun its data correction.
Other old DEV downloads resumed after shared-directory permissions were repaired;
origin investigation is recorded in the issue below. User has asked where they
came from, not yet instructed pausing/unmonitoring them. Do not claim they stayed
inactive. See `issues/2026-10-17-qbittorrent-existing-access.md`.
Use `~/git/homeserver/configs/dev/services/status-tracker/README.md` for the verified
backup, rollback image, and deployment process. Do not read server secrets or
print environment/configuration dumps. Never overwrite `.env` during source sync.

User also authorized deleting media in DEV when storage is needed. This does not
permit production media deletion. Verify dev targets and avoid removing media
needed by an active test; do not delete media merely to perform read-only checks.
