# Status Tracker agent entry point

Read `CLAUDE.md`, `inbox.txt`, the newest three `DIARY.md` entries and the handoff
they link, then `git status --short`. Global `~/git/AGENTS.md` and the shared app
conventions in `~/git/homeserver-apps/AGENTS.md` apply. App source and Compose
belong here; infrastructure and deployment notes belong in `~/git/homeserver`
(`configs/dev/services/status-tracker/README.md`); mechanics in `ops/README.md`.

Session state never lives in this file. The current resume point is the newest
diary entry; mid-task state goes in `handoffs/`.

## Working rules

FastAPI, SQLite, Jinja, HTMX and SSE; no stack migration planned.
Use `docs/TESTING.md`, extending existing regression/browser suites. Never use
real downloads or deletions as synthetic test fixtures.

User authorized DEV server work and deleting older DEV media if storage requires
it. Verify the target and preserve active test media. Older Kaguya media was
removed under that authorization; about 18 GiB remained at validation. Recheck
live capacity before another large download. Request20's validation files remain.

Production deployment and public status/announcements are user-gated. Never
read server secrets or print environment/configuration dumps. Never overwrite
`.env` during source sync. Use the infrastructure service README for backups and
rollback; older pre-season builds cannot safely correlate separated season rows.
