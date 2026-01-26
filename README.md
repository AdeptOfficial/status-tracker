# Status Tracker

Media request lifecycle tracker for Jellyseerr → Jellyfin pipeline.

## Overview

Receives webhooks from media services and correlates them to show the complete journey of a request:

```
Request → Indexed → Downloading → Importing → [Anime Matching] → Available
```

## Documentation

- **Feature plans:** `features/`
- **Known issues:** `issues/`
- **Technical docs:** `docs/`
- **Development log:** `DIARY.md`

## Current Status (2026-01-22)

### What Works
| Flow | Status | Notes |
|------|--------|-------|
| Regular Movies | ✅ Working | Full flow through Radarr |
| Regular TV Shows | ✅ Working | Full flow through Sonarr |
| Anime Movies | ✅ Working | Via Jellyfin fallback checker (polls every 30s) |
| Anime TV Shows | ❌ Broken | Stuck at IMPORTING - needs fallback checker extension |
| Deletion Sync | ✅ Working | Radarr, Sonarr, Shoko, Jellyfin confirmed |
| Jellyseerr Sync | ⚠️ Partial | Deletion works but ID resolution often fails |
| Library Sync | ⚠️ Partial | Adds new items but doesn't update missing IDs |

### Known Issues

**High Priority:**
- Anime TV shows stuck at IMPORTING state (`issues/design-separate-anime-movie-show-flows.md`)
- Library sync doesn't populate missing service IDs (`issues/library-sync-missing-ids.md`)
- Jellyseerr ID not captured on request creation (shows "not_needed" on deletion)

**Medium Priority:**
- Detail page SSE not updating download progress (`issues/detail-page-live-updates-bug.md`)
- Missing poster on detail page (`issues/detail-page-missing-poster.md`)
- Per-episode tracking not implemented (`issues/per-episode-download-tracking.md`)

See `issues/` folder for full list.

## Project Structure

```
app/
├── main.py              # FastAPI entry point
├── config.py            # Environment settings
├── database.py          # SQLite async setup
├── models.py            # MediaRequest, TimelineEvent, DeletionLog
├── schemas.py           # Pydantic schemas
├── core/
│   ├── plugin_base.py   # ServicePlugin base class
│   ├── state_machine.py # State transitions
│   ├── correlator.py    # Event matching
│   └── broadcaster.py   # SSE broadcasting
├── clients/
│   ├── qbittorrent.py   # qBittorrent API client
│   ├── jellyfin.py      # Jellyfin API (auth, deletion, verification)
│   ├── sonarr.py        # Sonarr API (deletion)
│   ├── radarr.py        # Radarr API (deletion)
│   ├── shoko.py         # Shoko SignalR client
│   └── jellyseerr.py    # Jellyseerr API (deletion)
├── services/
│   ├── auth.py          # Jellyfin token validation
│   ├── deletion_orchestrator.py  # Deletion coordination
│   ├── deletion_verifier.py      # Background verification
│   ├── jellyfin_verifier.py      # Fallback checker for stuck requests
│   ├── library_sync.py           # Sync existing Jellyfin library
│   └── timeout_checker.py        # Stale request detection
├── plugins/
│   ├── __init__.py      # Auto-loader
│   ├── jellyseerr.py    # Jellyseerr integration
│   ├── sonarr.py        # Sonarr webhooks
│   ├── radarr.py        # Radarr webhooks
│   ├── jellyfin.py      # Jellyfin webhooks
│   ├── shoko.py         # Shoko SignalR integration
│   └── qbittorrent.py   # qBittorrent polling + webhook
├── routers/
│   ├── webhooks.py      # POST /hooks/{service}
│   ├── api.py           # GET /api/*, deletion endpoints
│   ├── sse.py           # GET /api/sse (real-time updates)
│   └── pages.py         # HTML dashboard routes
└── templates/
    ├── base.html        # Base layout (Tailwind + htmx)
    ├── index.html       # Active requests page
    ├── detail.html      # Request detail + timeline + delete
    ├── history.html     # Completed requests + bulk delete
    ├── login.html       # Jellyfin authentication
    ├── deletion-logs.html  # Admin deletion audit log
    └── components/
        └── card.html    # Request card partial
```

## Implementation Status

### Core Features
| Part | Description | Status |
|------|-------------|--------|
| 1 | Foundation + Plugin Framework | ✅ Complete |
| 2 | Sonarr/Radarr Plugins | ✅ Complete |
| 3 | qBittorrent Plugin | ✅ Complete |
| 4 | Web Dashboard (htmx + Tailwind) | ✅ Complete |
| 5 | Real-Time Updates (SSE) | ⚠️ Partial (detail page bug) |
| 6 | Shoko Plugin (SignalR) | ⚠️ Partial (movies only) |
| 7 | Jellyfin Plugin | ✅ Complete |
| 8 | Polish & Error Handling | ⏳ In Progress |

### Deletion Sync Feature
| Part | Description | Status |
|------|-------------|--------|
| 1 | DeletionLog + DeletionSyncEvent models | ✅ Complete |
| 2 | Service API Clients (Radarr, Sonarr, Shoko, Jellyfin) | ✅ Complete |
| 3 | Auth Middleware (Jellyfin tokens) | ✅ Complete |
| 4 | Deletion Orchestrator | ✅ Complete |
| 5 | Delete API Endpoints | ✅ Complete |
| 6 | Dashboard Delete Button | ✅ Complete |
| 7 | History Bulk Delete | ✅ Complete |
| 8 | Shoko RemoveMissingFiles API | ✅ Complete |
| 9 | Jellyseerr Library Sync Trigger | ✅ Complete |
| 10 | Jellyseerr ID Resolution | ⚠️ Often fails (ID not stored on request) |
| 11 | Deletion Logs Page | ✅ Complete |

### Library Sync Feature
| Part | Description | Status |
|------|-------------|--------|
| 1 | Add new items from Jellyfin | ✅ Complete |
| 2 | Update existing items with missing IDs | ❌ Not implemented |
| 3 | Cross-reference with Radarr/Sonarr/Shoko | ❌ Not implemented |

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

### Network Requirements

Status-tracker needs to communicate with your media services. Create a shared Docker network:

```bash
docker network create media-net
```

Add this to your media stack's compose file and restart it:
```yaml
networks:
  default:
    name: media-net
    external: true
```

### Webhook Configuration

Configure each service to send webhooks to status-tracker:

| Service | URL | Events |
|---------|-----|--------|
| Jellyseerr | `http://status-tracker:8000/hooks/jellyseerr` | Pending, Approved |
| Sonarr | `http://status-tracker:8000/hooks/sonarr` | Grab, Download |
| Radarr | `http://status-tracker:8000/hooks/radarr` | Grab, Download |
| Jellyfin | `http://status-tracker:8000/hooks/jellyfin` | ItemAdded (requires Webhook plugin) |

**Note:** Shoko uses SignalR (configured via `SHOKO_*` env vars), not webhooks.

## API Documentation

FastAPI auto-generates interactive API docs:

| Endpoint | Description |
|----------|-------------|
| `/docs` | Swagger UI - interactive API explorer |
| `/redoc` | ReDoc - alternative API documentation |
| `/openapi.json` | OpenAPI schema (JSON) |

### Key API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/requests` | List all active requests |
| `GET` | `/api/requests/{id}` | Get request details + timeline |
| `GET` | `/api/history` | List completed requests |
| `GET` | `/api/health` | Health check (service connectivity) |
| `GET` | `/api/sse` | Server-Sent Events stream |
| `POST` | `/hooks/{service}` | Webhook receiver (jellyseerr, sonarr, radarr, jellyfin) |
| `DELETE` | `/api/requests/{id}` | Delete request from all services |
| `POST` | `/api/requests/bulk-delete` | Bulk delete from history |
| `POST` | `/api/library-sync` | Trigger Jellyfin library sync |

### Authentication

Most endpoints require a valid Jellyfin token passed via cookie (`jellyfin_token`).

Login at `/login` with your Jellyfin credentials.

## Troubleshooting

### Common Issues

**Container won't start**
```bash
docker compose logs status-tracker
# Check for missing env vars or connection errors
```

**Webhooks not received**
```bash
# Check container is on same network as media services
docker network inspect media-net

# Test webhook endpoint
curl -X POST http://localhost:8100/hooks/test -d '{}'
```

**Requests stuck at IMPORTING**
- Regular movies/TV: Check Jellyfin webhook plugin is installed and configured
- Anime movies: Should auto-resolve via fallback checker (30s polling)
- Anime TV: Known issue - fallback checker doesn't support TV yet

**Database locked error**
```bash
# Stop container
docker compose down

# Check for stale lock
ls -la data/

# Restart
docker compose up -d
```

**SSE not updating**
- History page: Should work
- Detail page: Known bug - use manual refresh
- Check browser console for connection errors

**Deletion fails for specific service**
```bash
# Check deletion logs
curl http://localhost:8100/api/deletion-logs

# Common causes:
# - Service API key missing/invalid in .env
# - ID not captured during initial request (shows "not_needed")
# - Service unreachable (check docker network)
```

**Health endpoint shows service down**
```bash
# Access health dashboard
curl http://localhost:8100/api/health

# Verify service connectivity from container
docker exec status-tracker curl http://sonarr:8989/api/v3/system/status
```

### Debug Mode

Enable verbose logging:
```bash
# In .env
LOG_LEVEL=DEBUG

# Restart
docker compose up -d --force-recreate
```

### Getting Help

1. Check `issues/` folder for known issues
2. Read `DIARY.md` for recent changes and fixes
3. Check `docs/` for technical deep-dives
