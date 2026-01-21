# Claude Context: Status-Tracker

Media request lifecycle tracker for Jellyseerr → Jellyfin pipeline.

## Overview

Real-time dashboard tracking media requests through:
```
Request → Indexed → Downloading → Importing → [Anime Matching] → Available
```

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
│   └── templates/           # Jinja2 HTML (htmx + Tailwind)
├── docker-compose.yml       # Deployment config
├── .env.template            # Environment variables template
├── Dockerfile
├── docs/                    # Technical documentation
├── issues/                  # Bug tracking
└── features/                # Feature planning
```

## Development

```bash
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8100
```

## Deployment

```bash
cp .env.template .env
# Edit .env with your values
docker compose up -d --build
```

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
