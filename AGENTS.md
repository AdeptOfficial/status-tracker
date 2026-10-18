# Status Tracker agent entry point

Read `CLAUDE.md`, `inbox.txt`, newest `DIARY.md`, `docs/ROADMAP.md` and git status.
Global `~/git/AGENTS.md` applies. Preserve unrelated work.

Current stack: FastAPI, SQLite, Jinja, HTMX and SSE. No stack migration planned.
Testing instructions: `docs/TESTING.md`. Extend the existing regression suite and
permanent browser suite; never use real media downloads/deletions as fixtures.

October 17 episode progress is deployed to DEV only. User explicitly said to stay
in dev and not push to production. Git commits/pushes do not authorize deployment.
DEV request 20 completed download/import/matching and reached Available after a
manual Jellyfin library refresh. User confirmed playback works on October18.
Next task: investigate and repair the automatic Shoko-to-Jellyfin refresh handoff.
Read `issues/2026-01-22-anime-matching-no-scan.md` October18 handoff first; it records
verified evidence, proposed implementation, tests and limitations. January code
snippets are historical, not a confirmed current root cause.
Request20 used 12 hardlinked files; force-start removed. Do not rerun its data
correction. Import repair: `issues/2026-10-17-dev-import-permissions.md`.
The read-only watcher `status-tracker-dev-request20.service` stops on Available;
it is no longer required. Its /tmp observation files are not durable evidence.
User wrapped up for the night; no further runtime changes made for this handoff.
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
