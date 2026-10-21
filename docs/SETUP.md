# Setup reference

Moved out of the README on 2026-10-20: project layout, network requirements and
webhook configuration. Deployment mechanics: `../ops/README.md`.

## Project structure

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
    ├── base.html        # Base layout (AdepT token CSS + htmx)
    ├── index.html       # Active requests page
    ├── detail.html      # Request detail + timeline + delete
    ├── history.html     # Completed requests + bulk delete
    ├── login.html       # Jellyfin authentication
    ├── deletion-logs.html  # Admin deletion audit log
    └── components/
        └── card.html    # Request card partial
```


## Deployment details

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

