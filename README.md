# Status Tracker

Media request lifecycle tracker for Jellyseerr → Jellyfin pipeline.

## Overview

Receives webhooks from media services and correlates them to show the complete journey of a request:

```
Request → Indexed → Downloading → Importing → [Anime Matching] → Available
```

## Documentation

- **Feature plans:** `features/`
- **Technical docs:** `docs/`
- **Development log:** `DIARY.md`

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
│   ├── jellyfin.py      # Jellyfin API (auth, deletion)
│   ├── sonarr.py        # Sonarr API (deletion)
│   ├── radarr.py        # Radarr API (deletion)
│   └── jellyseerr.py    # Jellyseerr API (deletion)
├── services/
│   ├── auth.py          # Jellyfin token validation
│   ├── deletion_orchestrator.py  # Deletion coordination
│   ├── deletion_verifier.py      # Background verification
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
| 5 | Real-Time Updates (SSE) | ✅ Complete |
| 6 | Shoko Plugin (SignalR) | ✅ Complete |
| 7 | Jellyfin Plugin | ✅ Complete |
| 8 | Polish & Error Handling | ⏳ In Progress |

### Deletion Sync Feature
| Part | Description | Status |
|------|-------------|--------|
| 1 | DeletionLog + DeletionSyncEvent models | ✅ Complete |
| 2 | Service API Clients | ✅ Complete |
| 3 | Auth Middleware (Jellyfin tokens) | ✅ Complete |
| 4 | Deletion Orchestrator | ✅ Complete |
| 5 | Delete API Endpoints | ✅ Complete |
| 6 | Dashboard Delete Button | ✅ Complete |
| 7 | History Bulk Delete | ✅ Complete |
| 8 | External Deletion Webhooks | ✅ Code Ready |
| 9 | Deletion Logs Page | ✅ Complete |

**Current:** Testing deletion sync (see `DIARY.md` for details)

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
