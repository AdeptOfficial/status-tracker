# Status Tracker agent entry point

Read `CLAUDE.md`, `inbox.txt`, newest `DIARY.md`, `docs/ROADMAP.md` and git status.
Global `~/git/AGENTS.md` applies. Preserve unrelated work. App source and Compose
belong here; infrastructure/deployment notes belong in `~/git/homeserver`.

## Verified DEV state — October 20

- Image `status-tracker:verified-delete-20261020`; 226 runtime regressions pass. Permanent
  Firefox acceptance and actual DEV layouts at 320–2048px pass.
- Cyberpunk S1 tracker21/Jellyseerr151 reached Available 10/10 automatically after
  memory-cache clearing and scanning. All ten video paths readable; user confirmed
  S1E1 playback. S2 tracker22/Jellyseerr150 remains separately Approved.
- Separate season identities, grouped cards and related-season detail links work.
  TV availability requires verified episodes, not just a series directory.
- Durable refresh jobs use confirmed Shoko evidence, bounded retries/backoff and
  cache-task completion before scanning. No automatic VFS/media deletion.
  The metadata-task-only hypothesis failed; do not reinstate that dispatch.
- See `issues/resolved/2026-01-22-anime-matching-no-scan.md` and newest diary for
  evidence. Watcher completed; no observer is required for the finished S1 test.
- TV synchronized deletion is temporarily blocked to prevent whole-show deletion
  from season controls. Failures retain records. Scoped deletion/re-request remains
  open; see newest DIARY and deletion-integration-gaps issue.
- DEV Interstellar movie deletion passed: actual file/library/provider absence
  verified, audit70 Complete; old audit69 remains Incomplete. Fresh re-request is
  untested. Read docs/MEDIA-PERMISSIONS.md before deployment or permission work.
- Next work is in the roadmap. S2 and regular-media flows remain unverified on
  this build. Standalone anime sequels may use different provider numbering.

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
