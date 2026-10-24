# Claude Context: Status-Tracker

Media request lifecycle tracker for Jellyseerr → Jellyfin pipeline.

## Overview

Real-time dashboard tracking media requests through:
```
Request → Indexed → Downloading → Importing → [Anime Matching] → Available
```

## Inbox Processing (Check on Every Startup)

**IMPORTANT:** Read `inbox.txt` on startup and run `~/git/workflows/process-inbox.md`: one new `YYYY-MM-DD-slug.md` per line in `bugs/`, `issues/` or `features/`, regenerate the index, then remove only the processed lines (infrastructure items go to `~/git/homeserver/issues/`).

## Project Structure

```
status-tracker/
├── app/
│   ├── main.py              # FastAPI entry point
│   ├── config.py            # Environment settings
│   ├── database.py          # SQLite async
│   ├── models.py            # ORM models
│   ├── schemas.py           # Pydantic schemas
│   ├── core/                # Plugin framework, state machine
│   ├── clients/             # API clients (qBit, Sonarr, etc.)
│   ├── services/            # Background services
│   ├── plugins/             # Webhook handlers per service
│   ├── routers/             # FastAPI routes
│   ├── templates/           # Jinja2 HTML (htmx + AdepT token CSS)
│   └── static/              # style.css + emblem (branding: ~/git/adeptproductions/branding)
├── docker-compose.yml       # Deployment config
├── .env.template            # Environment variables template
├── Dockerfile
├── docs/                    # Technical documentation
├── bugs/ issues/ features/ # Tracker, one file per item; rules in ~/git/homeserver-apps/AGENTS.md
├── roadmap/                 # public-safe milestones
```

## Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

## Deployment

```bash
install -m 600 .env.template .env
# Edit .env with your values
docker compose up -d --build
```

### AdeptLab Infrastructure

**Quick deploy:** `~/git/homeserver/scripts/deploy-status-tracker.sh`

**Full docs:** `~/git/homeserver/configs/dev/services/status-tracker/README.md`

**Security:** `~/git/homeserver/context/core/security.md`

## Key Files

| Purpose | File |
|---------|------|
| Entry point | `app/main.py` |
| State transitions | `app/core/state_machine.py` |
| ID correlation | `app/core/correlator.py` |
| Webhook routing | `app/routers/webhooks.py` |
| Deploy config | `docker-compose.yml` |

## History

See `DIARY.md` for development log.
