# Status Tracker

Media request lifecycle tracker for Jellyseerr → Jellyfin pipeline.

## Overview

Receives webhooks from media services and correlates them to show the complete journey of a request:

```
Request → Indexed → Downloading → Importing → [Anime Matching] → Available
```

## Documentation

- **Runbook:** `ops/README.md` (run, deploy, database, rollback)
- **Setup reference:** `docs/SETUP.md` (project layout, network, webhooks)
- **API:** `docs/API.md` · **Troubleshooting:** `docs/TROUBLESHOOTING.md` · **Testing:** `docs/TESTING.md`
- **Tracker:** `bugs/`, `issues/`, `features/`, `roadmap/` (one file per item, see each README)
- **Development log:** `DIARY.md`

## Current status (2026-10-20)

DEV verified Cyberpunk S1 request-to-playback and one regular movie deletion.
Movie deletion now checks actual file and library removal before completion.
TV deletion is temporarily blocked until season scope is implemented. S2 import,
a fresh re-request cycle and anime deletion still need validation. Production
release requires owner approval; see [roadmap](roadmap/README.md).

Before enabling deletion, follow [media permissions and deletion setup](docs/MEDIA-PERMISSIONS.md).
It explains service identities, directory access, the disposable preflight,
verification behavior and recovery. Status Tracker does not need a media mount.

## Validation

Current DEV evidence and reproducible test commands are in
[testing](docs/TESTING.md). Historical January completion claims are superseded by
those results and the [release roadmap](roadmap/README.md).

## Local Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

## Deployment

```bash
# Copy template and fill in your values
cp .env.template .env

# Build and run
docker compose up -d --build
```

### Media permissions

Read the [setup guide](docs/MEDIA-PERMISSIONS.md) before enabling
`ENABLE_DELETION_SYNC`. A successful API response alone does not prove filesystem
access. Run the disposable preflight under each writer's actual numeric identity.

## Automated tests

Run `./run_tests.sh -q` for isolated regressions. Real Firefox checks use
`npm --prefix tests/browser ci --ignore-scripts` then `./run_browser_tests.sh`.
See [testing and dev review](docs/TESTING.md) for prerequisites, scope and limits.

## // codesign

<img src="https://raw.githubusercontent.com/AdeptOfficial/AdeptOfficial/main/assets/codesign-typing.svg" alt="// code-signed by AdepT_X · stay sad and dead <3">

<p align="right"><img src="https://raw.githubusercontent.com/AdeptOfficial/AdeptOfficial/main/assets/codesign.svg" alt="// code-signed by AdepT_X · stay sad and dead <3"></p>
