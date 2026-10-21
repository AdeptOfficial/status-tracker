# API reference

Moved out of the README on 2026-10-20.


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
| `POST` | `/api/requests/{id}/delete` | Delete request from all services |
| `POST` | `/api/requests/bulk-delete` | Bulk delete from history |
| `POST` | `/api/library-sync` | Trigger Jellyfin library sync |

### Authentication

Most endpoints require a valid Jellyfin token passed via cookie (`jellyfin_token`).

Login at `/login` with your Jellyfin credentials.

