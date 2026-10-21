# Status Tracker — operations runbook

How to build, run, deploy, verify and roll back this app on any host. Instance
state for the AdepT homelab (which LXC, last verified image, snapshot paths) lives
in `~/git/homeserver/configs/<env>/services/status-tracker/README.md`; the
promotion gate is `~/git/workflows/promote-to-prod.md`. Facts below come from
`docker-compose.yml`, `Dockerfile`, `.env.template` and the homeserver docs.

## Runtime shape

| Item | Value |
|------|-------|
| Process | `uvicorn app.main:app` on container port 8000, published on host port 8100 |
| Image | built from `Dockerfile` (python:3.12-slim, multi-stage, curl for the healthcheck) |
| Data | SQLite at `/config/tracker.db`, host volume `/opt/appdata/status-tracker` |
| Network | external Docker network `media-net`, shared with the media stack so service names resolve |
| Health | `GET /api/health` (compose healthcheck every 30 s) |
| Config | `.env` next to the compose file, from `.env.template`; never commit or print it |

Upstream services it talks to: qBittorrent, Jellyfin, Shoko, Sonarr, Radarr,
Jellyseerr. Hosts default to container names on dev and are IP addresses on prod.
Deletion sync is off by default (`ENABLE_DELETION_SYNC`); read
`docs/MEDIA-PERMISSIONS.md` and run `scripts/check-media-permissions.sh` before
enabling it.

## Run anywhere

```bash
docker network create media-net        # once, if the media stack has not created it
cp .env.template .env                  # fill in values
docker compose up -d --build
curl -f http://localhost:8100/api/health
```

## Database

| Item | Value |
|------|-------|
| Engine | SQLite (WAL), via `DATABASE_URL=sqlite:////config/tracker.db` |
| Data path | `/opt/appdata/status-tracker/tracker.db` on the host |
| Backup | app running: `sqlite3 tracker.db ".backup '/opt/backups/status-tracker-before-<tag>-<date>/tracker.db'"`; stopped app: copy the file |
| Integrity | `sqlite3 tracker.db "PRAGMA integrity_check;"` |
| Restore check | point `DATABASE_URL` at a copy of the backup in a disposable path and run `pytest` |
| Migrations | additive add-column logic at startup in `app/database.py`; no Alembic; never rename or drop |

Follow `~/git/workflows/database-change.md` before any schema change, repair or
restore. Backups contain request history only, but treat them as private.

## Before any deploy

```bash
pytest                                 # see docs/TESTING.md for the browser suite
```

Run the suite inside the exact image you will deploy when the change touches
runtime dependencies. Never use real downloads or deletions as fixtures.

## Deploy to DEV

Procedure: `~/git/workflows/deploy-to-dev.md`. Infra-side script, kept in the homeserver repo because it embeds this homelab's
hosts and LXC numbers:

```bash
~/git/homeserver/scripts/deploy-status-tracker.sh            # dev
~/git/homeserver/scripts/deploy-status-tracker.sh ~/path     # a feature checkout
```

It rsyncs the source (excluding `.git`, `.venv`, caches and `.env`) to the Proxmox
host, copies it into `/opt/status-tracker` in the LXC, runs
`docker compose up -d --build`, waits for the healthcheck and cleans up. The
container's `.env` and the data volume are untouched.

## Deploy to production

The same script accepts `--prod`, but production is **on hold** by user
decision and every promotion passes the gate in `~/git/workflows/promote-to-prod.md`
first: explicit authorization for this version, DEV verified, backup taken, verify
after, record. Do not run `--prod` or `--both` without that.

## Backup and rollback

Pattern used for every DEV release so far (see the homeserver service README):

1. Stop the app, copy data and source to a dated private folder, for example
   `/opt/backups/status-tracker-before-<tag>-<date>/`.
2. Tag the running image before replacing it: `docker tag <current> status-tracker:before-<tag>-<date>`.
3. Deploy; verify. To roll back: retag the saved image as the compose image name
   and run `docker compose up -d --no-build`.

Rules that have bitten before: a code rollback never needs a database restore
when the schema change was additive; **never restore an older full database over
newer activity**; review intervening writes first.

## Verify after a deploy

- `docker ps` shows `healthy`; `curl -f http://<host>:8100/api/health`.
- Open the dashboard; confirm "Live updates active" (SSE) and that a known request
  renders its current state.
- `docker logs status-tracker --tail 50` free of new errors.
- Record image tag, backup path and results in `DIARY.md` and the homeserver
  service README.

## Where things are

- Logs: container stdout (`docker logs status-tracker`).
- Database: `/opt/appdata/status-tracker/tracker.db` on the host; back up stopped
  or with an online SQLite backup.
- Webhooks arrive from Jellyseerr, Sonarr, Radarr and Shoko; their configuration
  is in those services, documented in the homeserver media-stack context.
