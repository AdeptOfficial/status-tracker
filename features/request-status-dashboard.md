# Media Request Status Dashboard

**Status:** In Progress (Part 1 Complete)
**Created:** 2026-01-17
**Last Updated:** 2026-01-17

## Implementation Progress

| Part | Description | Status | Files |
|------|-------------|--------|-------|
| 1 | Foundation + Plugin Framework | ✅ **Complete** | `apps/status-tracker/` |
| 2 | Sonarr/Radarr Plugins | ✅ **Complete** | `app/plugins/sonarr.py`, `radarr.py` |
| 3 | qBittorrent Plugin | ✅ **Complete** | `app/plugins/qbittorrent.py`, `app/clients/` |
| 4 | Web Dashboard (htmx + Tailwind) | ✅ **Complete** | `app/templates/`, `app/routers/pages.py` |
| 5 | Real-Time Updates (SSE) | ✅ **Complete** | `app/routers/sse.py`, updated templates |
| 6 | Shoko Plugin (SignalR) | ⏳ **In Progress** | `app/clients/shoko.py`, `app/plugins/shoko.py` |
| 7 | Jellyfin Plugin | 🔲 Pending | `app/plugins/jellyfin.py` |
| 8 | Polish & Error Handling | 🔲 Pending | Various |

**Deployment:** Not yet deployed - waiting for all plugins before testing

**Related files:**
- Source code: `apps/status-tracker/`
- Stack config: `configs/dev/stacks/monitor/`
- Service docs: `configs/dev/services/status-tracker/README.md`
- Media stack update: `configs/dev/stacks/media/docker-compose.yml` (networks section)

---

## Overview

Real-time web dashboard showing the lifecycle of media requests from Jellyseerr through to Jellyfin availability. Users see exactly where their request is in the pipeline without needing to understand the underlying services.

## User Story

1. User requests "The Batman (2022)" via Jellyseerr
2. User opens the Status Dashboard
3. Dashboard shows real-time progress:

```
╔══════════════════════════════════════════════════════════╗
║  Media Request Status Dashboard                          ║
╠══════════════════════════════════════════════════════════╣
║                                                          ║
║  🎬 The Batman (2022)                    [DOWNLOADING]   ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━ 67%          ║
║  📊 2.3 GB/s • ETA 4m 32s                                ║
║                                                          ║
║  Timeline:                                               ║
║  ✓ Requested        12:34 PM                             ║
║  ✓ Approved         12:35 PM                             ║
║  ✓ Found            12:36 PM (1080p BluRay)              ║
║  ⟳ Downloading      12:37 PM (67% complete)              ║
║  ⏳ Importing        Pending...                           ║
║  ⏳ Available        Pending...                           ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
```

---

## Architecture

```
┌─────────────┐
│  Jellyseerr │ (User requests media)
└──────┬──────┘
       │ Webhook: request/approved/available
       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Status Tracker Service                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  ┌──────────────────┐    ┌──────────────────┐                  │
│  │  Webhook Routes  │    │   Frontend API   │                  │
│  │  (services push) │    │  (dashboard gets)│                  │
│  └────────┬─────────┘    └────────┬─────────┘                  │
│           │                       │                             │
│           ▼                       ▼                             │
│  ┌─────────────────────────────────────────┐                   │
│  │           Core State Manager            │                   │
│  │  - Correlates events by ID chain        │                   │
│  │  - Updates request states               │                   │
│  │  - Broadcasts changes via SSE           │                   │
│  └────────────────────┬────────────────────┘                   │
│                       │                                         │
│                       ▼                                         │
│              ┌─────────────────┐                                │
│              │     SQLite      │                                │
│              └─────────────────┘                                │
│                                                                 │
│  ┌──────────────────┐                                          │
│  │  Polling Service │ ──► qBittorrent (progress during DL)     │
│  └──────────────────┘                                          │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
       ▲           │
   Webhooks    SSE Stream
       │           │
       │           ▼
       │    ┌──────────────┐
       │    │  Web UI      │
       │    │  (Dashboard) │
       │    └──────────────┘
       │
       ├─── Sonarr/Radarr (webhooks: Grab, Download)
       ├─── qBittorrent (webhook via "run on complete" + API polling)
       ├─── Shoko (webhook: FileMatched - anime only)
       └─── Jellyfin (webhook: ItemAdded)
```

---

## Tech Stack

All free and self-hosted:

| Component | Tool | License |
|-----------|------|---------|
| Backend | Python + FastAPI | MIT |
| Database | SQLite | Public Domain |
| Real-time | SSE (Server-Sent Events) | Browser-native |
| Frontend | htmx + Tailwind | MIT |
| Container | Docker | Apache 2.0 |

**No cloud dependencies. Runs entirely on Proxmox.**

---

## Deployment

**Lives in the media stack** - same `docker-compose.yml` as Sonarr, Radarr, etc.

```
configs/dev/
├── stacks/
│   └── media/
│       ├── docker-compose.yml    ← Add status-tracker service here
│       └── .env.template         ← Add status-tracker env vars
│
└── services/
    └── status-tracker/           ← Documentation + app configs
        └── README.md
```

**Why same stack?**
- Shared Docker network (use container names like `http://sonarr:8989`)
- Simple webhook URLs (`http://status-tracker:8000/hooks/sonarr`)
- Logical grouping - this IS part of the media pipeline
- If media stack is down, dashboard has nothing to show anyway

---

## Request States

```
REQUESTED → APPROVED → SEARCHING → INDEXED → DOWNLOADING → DOWNLOAD_DONE → IMPORTING → [ANIME_INDEXING] → AVAILABLE → COMPLETED
```

| State | Trigger | User Sees |
|-------|---------|-----------|
| REQUESTED | Jellyseerr `MEDIA_PENDING` webhook | "Requested" |
| APPROVED | Jellyseerr `MEDIA_APPROVED` webhook | "Approved" |
| SEARCHING | Implicit (approved, waiting for grab) | "Searching..." |
| INDEXED | Sonarr/Radarr `Grab` webhook | "Found (1080p BluRay)" |
| DOWNLOADING | qBittorrent API poll (progress > 0) | "Downloading 67%" |
| DOWNLOAD_DONE | qBittorrent "run on complete" webhook | "Downloaded" |
| IMPORTING | Sonarr/Radarr `Download` webhook | "Importing..." |
| ANIME_INDEXING | Shoko webhook (event-driven, anime only) | "Matching..." |
| AVAILABLE | Jellyfin `ItemAdded` / Jellyseerr `MEDIA_AVAILABLE` | "Ready to watch!" |
| COMPLETED | Final state | Archived |

### Anime Detection

**Event-driven, not predictive.** If Shoko sends a webhook, it's anime. No webhook = not anime.

```python
def on_shoko_webhook(event):
    request = find_request_by_path(event.file_path)
    request.add_step("ANIME_INDEXING", status="in_progress")
```

The timeline builds itself based on which webhooks fire.

---

## API Design

### Webhook Routes (services → tracker)

```
POST /hooks/jellyseerr      # Request created/approved/available
POST /hooks/sonarr          # Grab, Download
POST /hooks/radarr          # Grab, Download
POST /hooks/qbittorrent     # Download complete (from "run on finish")
POST /hooks/shoko           # File matched (anime only)
POST /hooks/jellyfin        # Item added
```

### Frontend API (dashboard → tracker)

```
GET  /api/requests                    # List all active requests
GET  /api/requests/{id}               # Single request detail
GET  /api/requests/{id}/timeline      # Timeline events for request
GET  /api/requests?user={user}        # Filter by user
GET  /api/requests?status={status}    # Filter by state

GET  /api/sse                         # SSE stream for real-time updates
```

### Utility

```
GET  /api/health                      # Service health check
POST /api/requests/{id}/retry         # Manual retry failed request
```

---

## Correlation Strategy

The hardest part: tracking the same request across different service IDs.

```
Jellyseerr Request #42 (tmdbId: 414906)
    ↓ matched by tmdbId
Radarr Movie (tmdbId: 414906, downloadId: "abc123def")
    ↓ downloadId = qBittorrent hash
qBittorrent (hash: "abc123def", save_path: "/downloads/The.Batman.2022")
    ↓ matched by file path
Shoko (file: "/downloads/The.Batman.2022/..." - if anime)
    ↓ matched by path
Jellyfin (path-based or library scan event)
```

### Database Schema

```sql
CREATE TABLE requests (
    id INTEGER PRIMARY KEY,
    jellyseerr_id INTEGER UNIQUE,
    tmdb_id INTEGER,
    tvdb_id INTEGER,
    media_type TEXT,  -- 'movie' or 'tv'
    title TEXT,
    user_id TEXT,

    -- Current state
    state TEXT,
    state_updated_at TIMESTAMP,
    progress REAL,  -- 0.0 to 1.0 for downloads

    -- Correlation IDs (populated as events arrive)
    sonarr_id INTEGER,
    radarr_id INTEGER,
    qbit_hash TEXT,
    shoko_id INTEGER,
    jellyfin_id TEXT,

    created_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE timeline_events (
    id INTEGER PRIMARY KEY,
    request_id INTEGER REFERENCES requests(id),
    state TEXT,
    timestamp TIMESTAMP,
    details TEXT  -- JSON: quality, indexer, speed, etc.
);
```

---

## UI Design

### User-Friendly Language

| Technical | User Sees |
|-----------|-----------|
| Prowlarr searched 6 indexers | (hidden) |
| Grabbed from TorrentLeech | "Found (1080p BluRay)" |
| qBittorrent downloading | "Downloading 67% • 2.3 GB/s" |
| Sonarr importing | "Importing..." |
| Shoko AniDB matching | "Matching..." |
| Jellyfin library scan | "Ready to watch!" |

### Conditional Flows

**Movies/TV (non-anime):**
```
✓ Requested
✓ Approved
✓ Found
✓ Downloading
✓ Imported
✓ Available
```

**Anime (Shoko webhook fires):**
```
✓ Requested
✓ Approved
✓ Found
✓ Downloading
✓ Imported
⟳ Matching      ← Appears only when Shoko fires
⏳ Available
```

### Error States

```
╔══════════════════════════════════════════════════════════╗
║  🎬 Some Obscure Movie (2019)              [FAILED]      ║
║  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━              ║
║  ⚠️ No releases found matching quality profile           ║
║                                                          ║
║  ✓ Requested        2:15 PM                              ║
║  ✓ Approved         2:15 PM                              ║
║  ✗ Searching        2:16 PM - No results                 ║
║                                                          ║
║  [🔄 Retry Search]  [📝 Lower Quality]  [❌ Cancel]      ║
╚══════════════════════════════════════════════════════════╝
```

### Mobile View

Simple stacking cards:

```
┌──────────────────────┐
│ The Batman (2022)    │
│ ████████░░░░ 67%     │
│ Downloading • 4m     │
└──────────────────────┘
┌──────────────────────┐
│ Demon Slayer S4      │
│ ████████████ 100%    │
│ ✓ Ready to watch     │
└──────────────────────┘
```

---

## Service Integration Details

### Jellyseerr

**Webhooks:** `MEDIA_PENDING`, `MEDIA_APPROVED`, `MEDIA_AVAILABLE`, `MEDIA_FAILED`

**Payload includes:** `media.tmdbId`, `media.tvdbId`, `request.requestedBy`, `media.status`

**API:** `GET /api/v1/request`, `GET /api/v1/request/{id}`

---

### Sonarr / Radarr

**Webhooks:** `Grab` (found + sent to download client), `Download` (importing)

**Key payload fields:**
- `movie.tmdbId` / `series.tvdbId` - correlation with Jellyseerr
- `downloadId` - qBittorrent hash (critical for correlation!)
- `release.indexer` - which indexer found it
- `release.quality` - quality profile matched

**API:** `GET /api/v3/queue`, `GET /api/v3/movie`, `GET /api/v3/series`

---

### qBittorrent

**Webhooks:** None built-in, but "Run external program on torrent finished":

```bash
curl -X POST http://status-tracker:8000/hooks/qbittorrent \
  -H "Content-Type: application/json" \
  -d '{"hash": "%I", "name": "%N", "path": "%F", "size": "%Z"}'
```

**API (for progress polling):**
- `POST /api/v2/auth/login` - get session
- `GET /api/v2/torrents/info?hashes={hash}` - progress, speed, ETA

---

### Shoko

**Webhooks:** `FileMatched`, `SeriesComplete`

**Correlation:** Match by file path (same directories Sonarr outputs to)

**API:** `GET /api/v3/File`, `GET /api/v3/Series`

---

### Jellyfin

**Webhooks (via plugin):** `ItemAdded`, `LibraryScanProgress`

**API:** `GET /Items`, `POST /Library/Refresh`

---

## Implementation Plan

### Part 1: Foundation ✅ COMPLETE

**Goal:** Basic service that receives webhooks and stores state

- [x] Project scaffolding (FastAPI, SQLite, Docker)
- [x] Database schema (requests, timeline_events)
- [x] Health check endpoint
- [x] Jellyseerr webhook handler (REQUESTED, APPROVED)
- [x] Basic `/api/requests` endpoint
- [x] Docker Compose integration (separate monitor stack with shared network)
- [x] `.env.template` with required variables
- [x] Plugin architecture for extensibility

**Deliverable:** Service starts, receives Jellyseerr webhooks, stores in DB, basic API works.

**Files created:**
- `apps/status-tracker/` - Full application source
- `configs/dev/stacks/monitor/docker-compose.yml`
- `configs/dev/services/status-tracker/README.md`

---

### Part 2: Sonarr/Radarr Integration ✅ COMPLETE

**Goal:** Track grab and import events

- [x] Sonarr webhook handler (Grab, Download)
- [x] Radarr webhook handler (Grab, Download)
- [x] Correlation logic (match by tmdbId/tvdbId)
- [x] Store downloadId (qBit hash) from Grab events
- [x] Update state machine (APPROVED → INDEXED → IMPORTING)
- [x] Timeline events table population

**Deliverable:** Full tracking from request to import (minus download progress).

**Files created:**
- `apps/status-tracker/app/plugins/sonarr.py`
- `apps/status-tracker/app/plugins/radarr.py`
- Updated `app/core/state_machine.py` (added INDEXED → IMPORTING transition)

---

### Part 3: qBittorrent Progress ✅ COMPLETE

**Goal:** Real-time download progress

- [x] qBittorrent API client (auth, torrent info)
- [x] Polling service (watch active hashes)
- [x] Progress updates to database
- [x] qBittorrent "run on complete" webhook handler
- [x] DOWNLOADING and DOWNLOAD_DONE states

**Deliverable:** Live download percentage, speed, ETA in database.

**Files created:**
- `apps/status-tracker/app/clients/__init__.py`
- `apps/status-tracker/app/clients/qbittorrent.py` - Async API client with auth, torrent info
- `apps/status-tracker/app/plugins/qbittorrent.py` - Webhook handler + polling
- Updated `app/main.py` - Background polling task
- Updated `app/database.py` - Added `async_session` alias

---

### Part 4: Web Dashboard (Basic) ✅ COMPLETE

**Goal:** Viewable UI

- [x] HTML templates (htmx + Tailwind)
- [x] Request list page
- [x] Request detail page with timeline
- [x] Basic styling (cards, progress bars)
- [x] Mobile-responsive layout

**Deliverable:** Functional dashboard showing all requests and their states.

**Files created:**
- `apps/status-tracker/app/routers/pages.py` - HTML page routes
- `apps/status-tracker/app/templates/base.html` - Base layout with Tailwind CDN, htmx
- `apps/status-tracker/app/templates/index.html` - Active requests list
- `apps/status-tracker/app/templates/detail.html` - Request detail with timeline
- `apps/status-tracker/app/templates/components/card.html` - Request card partial

**Features:**
- Dark theme with Tailwind styling
- Request cards with poster, title, progress bar
- State badges with color coding
- Timeline view on detail page
- Auto-polling every 5s (replaced by SSE in Part 5)
- Mobile-responsive grid layout

---

### Part 5: Real-Time Updates ✅ COMPLETE

**Goal:** Live updates without refresh

- [x] SSE endpoint (`/api/sse`)
- [x] Broadcast state changes to connected clients
- [x] htmx SSE integration (via native EventSource + htmx.trigger)
- [x] Auto-update progress bars
- [x] Connection handling (reconnect with exponential backoff)

**Deliverable:** Dashboard updates in real-time as events happen.

**Files created:**
- `apps/status-tracker/app/routers/sse.py` - SSE endpoint using sse-starlette

**Files updated:**
- `apps/status-tracker/app/templates/index.html` - SSE connection, refresh on update events
- `apps/status-tracker/app/templates/detail.html` - SSE connection, targeted refresh for specific request
- `apps/status-tracker/app/templates/base.html` - Cleaned up footer
- `apps/status-tracker/app/routers/__init__.py` - Export sse_router
- `apps/status-tracker/app/main.py` - Include sse_router

**Features:**
- Connection status indicator (green=connected, red=disconnected)
- Shows brief "Updated: Title" feedback when updates arrive
- Exponential backoff reconnection (3s, 6s, 9s... up to 5 attempts)
- Native EventSource API (browser auto-handles reconnection)
- htmx integration via custom event trigger (`sse:refresh`)

---

### Part 6: Shoko Integration (Anime) 🔲 IN PROGRESS

**Goal:** Anime-specific tracking

**Research findings (2026-01-17):**
- Shoko does NOT have built-in webhooks - uses **SignalR** for real-time events
- Path correlation verified: both Sonarr and Shoko see `/data/...` paths
- Best library: [pysignalr](https://pypi.org/project/pysignalr/) (Python 3.10+, actively maintained)

**Implementation approach:** SignalR client (not webhooks)
- [ ] Add `pysignalr` to requirements.txt
- [ ] Create Shoko SignalR client (`app/clients/shoko.py`)
- [ ] Connect to Shoko's SignalR hub on startup
- [ ] Listen for file matched events
- [ ] Correlation by file path (match against `final_path` from Sonarr)
- [ ] ANIME_MATCHING state transition
- [ ] Handle multiple concurrent anime requests correctly (title verification)

**Correlation strategy:**
```
Sonarr stores: /data/anime/shows/DAN DA DAN/Season 01/episode.mkv (final_path)
Shoko reports: /data/anime/shows/DAN DA DAN/Season 01/episode.mkv (SignalR event)
Match on: exact path or filename + parent directory
```

**Deliverable:** Anime requests show Shoko "Matching" step in real-time.

**Files to create:**
- `apps/status-tracker/app/clients/shoko.py` - SignalR client
- `apps/status-tracker/app/plugins/shoko.py` - Event handler

---

### Part 7: Jellyfin Integration 🔲 PENDING

**Goal:** Confirm availability

- [ ] Jellyfin webhook handler (ItemAdded)
- [ ] Mark requests as AVAILABLE
- [ ] Link to Jellyfin item (deep link)
- [ ] Generate "Watch Now" URLs

**Deliverable:** Full end-to-end tracking from request to playable.

**Files to create:**
- `apps/status-tracker/app/plugins/jellyfin.py`

---

### Part 8: Polish & Error Handling 🔲 PENDING

**Goal:** Production-ready

- [ ] Error states (FAILED, timeout handling)
- [ ] Retry functionality
- [ ] User filtering (show "my requests")
- [ ] Request history/archive view
- [ ] Logging and debugging tools
- [ ] Documentation

**Deliverable:** Robust, user-friendly dashboard.

**Files to create:**
- `apps/status-tracker/app/services/timeout_checker.py`
- `apps/status-tracker/app/templates/history.html`

---

### Future (Phase 2)

- [ ] Jellyfin plugin for in-app notifications
- [ ] Push notifications (Gotify/ntfy)
- [ ] Multi-episode TV progress (4/12 episodes)
- [ ] Statistics (avg completion time, success rate)
- [ ] Admin view (all users, system health)

---

## Open Questions

- [ ] Auth strategy? (Open on LAN → Jellyfin SSO later)
- [ ] How long to keep completed requests? (7 days? 30 days?)
- [ ] Multi-episode handling - aggregate or per-episode tracking?
- [ ] Timeout thresholds for stuck states?

---

## References

- [Jellyseerr API](https://api-docs.overseerr.dev/)
- [Sonarr API](https://sonarr.tv/docs/api/)
- [Radarr API](https://radarr.video/docs/api/)
- [qBittorrent WebUI API](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1))
- [Shoko API](https://docs.shokoanime.com/api/)
- [Jellyfin API](https://api.jellyfin.org/)
