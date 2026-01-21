# Claude Context: Status-Tracker

Media request lifecycle tracker for Jellyseerr → Jellyfin pipeline.

## Overview

Real-time dashboard tracking media requests through:
```
Request → Indexed → Downloading → Importing → [Anime Matching] → Available
```

## Inbox Processing (Check on Every Startup)

**IMPORTANT:** Always read `inbox.txt` on startup for quick notes from the user.

**Workflow:**
1. Read `inbox.txt` for items under "Issues:" or "Features:"
2. Process each item → create markdown in `features/` or `issues/`
3. **Clear processed items from `inbox.txt`** after creating the tracking file
4. Update `DIARY.md` if significant

**After processing:** Remove the item text from inbox.txt, leaving only the section headers.

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
