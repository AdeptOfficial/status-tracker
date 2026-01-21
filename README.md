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

## Current Status (2026-01-21)

### What Works
| Flow | Status | Notes |
|------|--------|-------|
| Regular Movies | ✅ Working | Full flow through Radarr |
| Regular TV Shows | ✅ Working | Full flow through Sonarr |
| Anime Movies | ✅ Working | Via Jellyfin fallback checker (polls every 30s) |
| Anime TV Shows | ❌ Broken | Stuck at IMPORTING - needs fallback checker extension |
| Deletion Sync | ⚠️ Partial | Works but has gaps (see Known Issues) |
| Library Sync | ⚠️ Partial | Adds new items but doesn't update missing IDs |

### Known Issues (26 tracked)

**High Priority:**
- Anime TV shows stuck at IMPORTING state (`issues/design-separate-anime-movie-show-flows.md`)
- Library sync doesn't populate missing service IDs (`issues/library-sync-missing-ids.md`)
- Deletion sync has gaps with Shoko/Jellyseerr (`issues/deletion-integration-gaps.md`)

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
| 2 | Service API Clients | ✅ Complete |
| 3 | Auth Middleware (Jellyfin tokens) | ✅ Complete |
| 4 | Deletion Orchestrator | ✅ Complete |
| 5 | Delete API Endpoints | ✅ Complete |
| 6 | Dashboard Delete Button | ✅ Complete |
| 7 | History Bulk Delete | ✅ Complete |
| 8 | External Deletion Webhooks | ⚠️ Has gaps |
| 9 | Deletion Logs Page | ✅ Complete |

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
