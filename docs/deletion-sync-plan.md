# Media Deletion Sync Feature - Implementation Plan

## Overview

Add media deletion management to status-tracker dashboard with:
1. Deletion logging (who deleted what, from which tool)
2. Admin-only deletion from dashboard UI
3. Full service sync when media is deleted
4. Bulk delete capability in history view

**Key Constraints:**
- NO edits to external services (Sonarr, Radarr, Jellyfin, etc.) - only status-tracker
- Additive changes only - no breaking existing functionality
- Test after each part before proceeding

**Current Status Note:**
Dashboard is still being tested - there are existing issues with file sync after download. This deletion feature should be developed in parallel without breaking the core request tracking functionality. Each part must verify existing endpoints still work.

---

## Architecture Decision

**Extend status-tracker** (not a new service) because:
- Existing plugin system handles multi-service coordination
- State machine already manages transitions with timeline logging
- SSE broadcaster ready for real-time UI updates
- Single deployment, no inter-service complexity

**Deletion Model: Hard Delete + DeletionLog**
- Remove request from `requests` table entirely (not soft delete)
- Create `DeletionLog` entry for audit trail
- Normal users never see deleted items (they don't exist in requests)
- If same media is re-requested later → creates brand new fresh request

---

## Implementation Parts

### Part 1: Database Schema - DeletionLog Model
**Goal:** Add DeletionLog model and new correlation fields without breaking existing functionality.

**Files to modify:**
| File | Changes |
|------|---------|
| `app/models.py` | Add `DeletionLog`, `DeletionSyncEvent` models, `DeletionSource`, `ServiceSyncStatus` enums, add `sonarr_id`/`radarr_id`/`shoko_series_id`/`jellyseerr_id` fields to MediaRequest |
| `app/schemas.py` | Add `DeletionLogResponse`, `DeletionSyncEventResponse` schemas |

**Note:** NO changes to RequestState enum - we're doing hard delete, not adding DELETED state.

**New Enum - DeletionSource:**
```python
class DeletionSource(str, enum.Enum):
    DASHBOARD = "dashboard"    # Deleted via status-tracker UI
    SONARR = "sonarr"          # Detected via Sonarr webhook
    RADARR = "radarr"          # Detected via Radarr webhook
    JELLYFIN = "jellyfin"      # Detected via Jellyfin webhook
    SHOKO = "shoko"            # Detected via Shoko SignalR
    EXTERNAL = "external"      # Unknown source, detected via sync check
```

**New Enum - ServiceSyncStatus:**
```python
class ServiceSyncStatus(str, enum.Enum):
    PENDING = "pending"           # Not yet attempted
    ACKNOWLEDGED = "acknowledged" # API call sent, waiting for response
    CONFIRMED = "confirmed"       # API returned success
    VERIFIED = "verified"         # CLI check confirmed deletion
    FAILED = "failed"             # API returned error
    SKIPPED = "skipped"           # Service not applicable (e.g., Shoko for non-anime)
    NOT_NEEDED = "not_needed"     # Service didn't have this item
```

**New Model - DeletionLog:**
```python
class DeletionLog(Base):
    """Audit log for deleted media with per-service sync tracking."""
    __tablename__ = "deletion_logs"

    id: int (PK)

    # Snapshot of what was deleted (copied from request before deletion)
    title: str
    media_type: MediaType
    tmdb_id: Optional[int]
    tvdb_id: Optional[int]
    jellyfin_id: Optional[str]
    sonarr_id: Optional[int]
    radarr_id: Optional[int]
    shoko_series_id: Optional[int]
    jellyseerr_id: Optional[int]
    poster_url: Optional[str]
    year: Optional[int]

    # Who/what initiated deletion
    source: DeletionSource
    deleted_by_user_id: Optional[str]   # Jellyfin user ID
    deleted_by_username: Optional[str]  # Resolved username

    # Timestamps
    initiated_at: datetime              # When deletion was requested
    completed_at: Optional[datetime]    # When ALL services confirmed

    # Relationships
    sync_events: list["DeletionSyncEvent"]  # Per-service timeline
```

**New Model - DeletionSyncEvent (Timeline):**
```python
class DeletionSyncEvent(Base):
    """Individual service sync event in deletion timeline."""
    __tablename__ = "deletion_sync_events"

    id: int (PK)
    deletion_log_id: int (FK → deletion_logs.id)

    # Which service
    service: str  # "jellyfin", "sonarr", "radarr", "shoko", "jellyseerr"

    # Status progression
    status: ServiceSyncStatus

    # Details
    details: Optional[str]      # Human-readable message
    error_message: Optional[str] # If failed, why
    api_response: Optional[str]  # Raw API response (JSON)

    # Timestamp
    timestamp: datetime
```

**Example Timeline for a Movie Deletion:**
```
DeletionLog #42: "Interstellar (2014)"
├── initiated_at: 2026-01-18 14:30:00
├── source: DASHBOARD
├── deleted_by: "admin" (user_id: abc123)
│
└── sync_events:
    ├── [14:30:01] radarr    ACKNOWLEDGED  "DELETE request sent"
    ├── [14:30:02] radarr    CONFIRMED     "API returned 200 OK"
    ├── [14:30:03] jellyfin  ACKNOWLEDGED  "DELETE request sent"
    ├── [14:30:03] jellyfin  CONFIRMED     "API returned 204 No Content"
    ├── [14:30:04] shoko     SKIPPED       "Not an anime title"
    ├── [14:30:05] jellyseerr ACKNOWLEDGED "DELETE request sent"
    ├── [14:30:05] jellyseerr CONFIRMED   "Request removed"
    ├── [14:32:00] radarr    VERIFIED     "CLI check: file not found on disk"
    └── [14:32:01] jellyfin  VERIFIED     "CLI check: item not in library"

completed_at: 2026-01-18 14:32:01 (all verified)
```

**New fields on MediaRequest (for deletion API calls):**
```python
# Add to MediaRequest model
sonarr_id: Optional[int]  # Sonarr series/movie internal ID
radarr_id: Optional[int]  # Radarr movie internal ID
shoko_series_id: Optional[int]  # Shoko series ID (for anime)
```

---

### Part 2: Service API Clients
**Goal:** Create clients to call deletion APIs on external services.

**Files to create:**
| File | Purpose |
|------|---------|
| `app/clients/jellyfin.py` | Delete items, get user info, validate tokens |
| `app/clients/sonarr.py` | Delete series, trigger rescan |
| `app/clients/radarr.py` | Delete movies, trigger rescan |

**New config in `app/config.py`:**
```python
# Jellyfin API (for deletion and user lookup)
JELLYFIN_HOST: str = "jellyfin"
JELLYFIN_PORT: int = 8096
JELLYFIN_API_KEY: str = ""  # Admin API key

# Sonarr API
SONARR_HOST: str = "sonarr"
SONARR_PORT: int = 8989
SONARR_API_KEY: str = ""

# Radarr API
RADARR_HOST: str = "radarr"
RADARR_PORT: int = 7878
RADARR_API_KEY: str = ""

# Admin users (comma-separated Jellyfin user IDs)
ADMIN_USER_IDS: str = ""  # e.g., "abc123,def456"

# Feature flag
ENABLE_DELETION_SYNC: bool = False  # Enable after testing
```

---

### Part 3: Auth Middleware & Admin Validation
**Goal:** Add authentication to identify users and check admin status.

**Files to create/modify:**
| File | Changes |
|------|---------|
| `app/services/auth.py` | Create - validate Jellyfin tokens, check admin status |
| `app/routers/api.py` | Add auth dependency to deletion endpoints |

**Auth Flow:**
1. Dashboard sends Jellyfin token in `X-Jellyfin-Token` header
2. Auth service validates token against Jellyfin API
3. Returns user info including admin status
4. Admin status checked against `ADMIN_USER_IDS` in config

---

### Part 4: Deletion Orchestrator Service
**Goal:** Coordinate deletion across all services (hard delete from DB + sync external services).

**Files to create:**
| File | Purpose |
|------|---------|
| `app/services/deletion_orchestrator.py` | Main deletion logic - calls all service APIs |

**Deletion Flow (Hard Delete with Timeline Tracking):**
```
PHASE 1: INITIATE
1. Validate admin user (check X-Jellyfin-Token + ADMIN_USER_IDS)
2. Snapshot request data
3. Create DeletionLog entry (initiated_at = now)
4. Create initial DeletionSyncEvent for each applicable service (status: PENDING)
5. HARD DELETE request from requests table immediately
6. Broadcast SSE "deletion_started" with deletion_log_id

PHASE 2: SYNC SERVICES (async, tracked per-service)
For each service in order:

   Step A - Sonarr/Radarr (delete files):
   a) Create event: {service: "radarr", status: ACKNOWLEDGED, details: "DELETE request sent"}
   b) Call API: DELETE /api/v3/movie/{radarr_id}?deleteFiles=true
   c) On 200: Create event: {status: CONFIRMED, details: "API returned success"}
      On error: Create event: {status: FAILED, error_message: "..."}
   d) Broadcast SSE "deletion_progress"

   Step B - Shoko (anime metadata):
   a) If not anime: Create event: {status: SKIPPED, details: "Not an anime title"}
   b) Else: ACKNOWLEDGED → API call → CONFIRMED/FAILED
   c) Broadcast SSE "deletion_progress"

   Step C - Jellyfin (library entry):
   a) ACKNOWLEDGED → DELETE /Items/{jellyfin_id} → CONFIRMED/FAILED
   b) Broadcast SSE "deletion_progress"

   Step D - Jellyseerr (request):
   a) ACKNOWLEDGED → DELETE /api/v1/request/{id} → CONFIRMED/FAILED
   b) Broadcast SSE "deletion_progress"

PHASE 3: VERIFY (background task, runs after ~30 seconds)
For each service that was CONFIRMED:
   a) Check if item actually gone:
      - Radarr: GET /api/v3/movie/{id} → should return 404
      - Sonarr: GET /api/v3/series/{id} → should return 404
      - Jellyfin: GET /Items/{id} → should return 404
      - File system: Check path exists (if we stored it)
   b) On success: Create event: {status: VERIFIED, details: "CLI check confirmed deletion"}
   c) On failure: Create event: {status: FAILED, error_message: "Item still exists!"}

PHASE 4: COMPLETE
1. When all services are VERIFIED/SKIPPED/NOT_NEEDED:
   - Set DeletionLog.completed_at = now
2. Broadcast SSE "deletion_completed"
```

---

### Part 4b: Deletion Verification Service (Background Task)
**Goal:** Verify deletions actually completed by checking each service.

**Files to create:**
| File | Purpose |
|------|---------|
| `app/services/deletion_verifier.py` | Background task to verify deletions |

---

### Part 5: Delete API Endpoints
**Goal:** Add REST API for deletion operations.

**Endpoints:**
```
POST /api/requests/{id}/delete
  - Requires: Admin auth (X-Jellyfin-Token header)
  - Body: { "delete_files": true }
  - Returns: DeletionLogResponse
  - Effect: Hard deletes request from DB, creates DeletionLog

POST /api/requests/bulk-delete
  - Requires: Admin auth
  - Body: { "request_ids": [1, 2, 3], "delete_files": true }
  - Returns: list[DeletionLogResponse]

GET /api/deletion-logs
  - List recent deletions (admin only)
  - Query: page, per_page, source

GET /api/deletion-logs/{id}
  - Get single deletion log with sync status
```

---

### Part 6: Dashboard UI - Delete Button
**Goal:** Add delete button to detail view (admin only).

**UI Changes:**
- Delete button: Red, visible only to admins
- Confirmation modal shows what will be deleted
- After deletion: Redirects to history page (request no longer exists)

---

### Part 7: History Page Enhancement - Available Filter & Bulk Delete
**Goal:** Add state filter tabs and bulk selection for admins.

**UI Changes:**
```
[All] [Available ✓] [Failed] [Timeout]  ← Filter tabs (no "Deleted" - they're gone)

□ Select All                            ← Admin only, visible only in Available tab
┌─────────┐ ┌─────────┐ ┌─────────┐
│ □ Movie1│ │ □ Movie2│ │ □ Movie3│   ← Checkboxes on cards (admin only)
└─────────┘ └─────────┘ └─────────┘

[Delete Selected (3)]                   ← Floating action bar
```

---

### Part 8: External Deletion Detection (Webhooks)
**Goal:** Detect when media is deleted via Sonarr/Radarr/Jellyfin UI and sync.

**Files to modify:**
| File | Changes |
|------|---------|
| `app/plugins/sonarr.py` | Handle `SeriesDeleted`, `EpisodeFileDeleted` events |
| `app/plugins/radarr.py` | Handle `MovieDeleted`, `MovieFileDeleted` events |
| `app/plugins/jellyfin.py` | Handle `ItemRemoved` events |
| `app/clients/shoko.py` | Implement `_handle_file_deleted` callback |

**Flow for external deletion:**
```
External deletion (Sonarr UI) → Webhook → status-tracker
    ↓
1. Find matching MediaRequest by correlation ID (sonarr_id, tmdb_id, etc.)
2. Snapshot request data
3. Create DeletionLog (source=SONARR, deleted_by_username="External")
4. Sync OTHER services (skip the source that triggered)
5. HARD DELETE request from DB
6. Broadcast SSE "request_deleted" event
```

---

### Part 9: Deletion Log Page (Admin Only)
**Goal:** Add dedicated page showing deletion history for admins.

**Page Content:**
- Table of recent deletions
- Columns: Title, Type, Deleted By, Source, Sync Status, Date
- Click row → detail modal with full sync status per service
- Filter by source, date range
- Color-coded sync status (green=synced, red=failed, yellow=pending)

---

## Verified API Endpoints (from official docs)

**Sources:**
- [Sonarr API Docs](https://sonarr.tv/docs/api/)
- [Radarr API Docs](https://radarr.video/docs/api/)
- [Jellyfin GitHub PR #7615](https://github.com/jellyfin/jellyfin/pull/7615)
- [Overseerr API Docs](https://api-docs.overseerr.dev/)
- [Shoko GitHub](https://github.com/ShokoAnime/ShokoServer)

### Sonarr API v3
```
DELETE /api/v3/series/{id}?deleteFiles=true
Header: X-Api-Key: <api-key>
```
- `deleteFiles=true` → Deletes series folder and files from disk
- `deleteFiles=false` → Removes from DB only (keeps files)
- Response: 200 OK

### Radarr API v3
```
DELETE /api/v3/movie/{id}?deleteFiles=true
Header: X-Api-Key: <api-key>
```
- `deleteFiles=true` → Deletes movie files from disk
- `deleteFiles=false` → Removes from DB only (keeps files)
- Response: 200 OK

### Jellyfin API
```
DELETE /Items/{ItemId}
Header: X-Emby-Token: <api-key>
```
- **IMPORTANT:** Deletes library entry ONLY, does NOT delete files from disk
- Files must be deleted by Sonarr/Radarr first, then Jellyfin library refreshed
- Response: 204 No Content

### Shoko Server API v3
```
POST /api/v3/Action/RemoveMissingFiles/true
Header: X-API-KEY: <api-key>
```
- Removes entries for files no longer on disk from Shoko database
- Alternative: `POST /api/v3/ImportFolder/{folderId}/Scan` to rescan specific folder
- No direct "delete file" endpoint - Shoko detects deletions

### Jellyseerr API (Overseerr-compatible)
```
DELETE /api/v1/request/{requestId}
Header: X-Api-Key: <api-key>
```
- Removes request from Jellyseerr (does NOT delete from Sonarr/Radarr)
- Alternative: `POST /api/v1/request/{requestId}/decline` to decline instead of delete
- Response: 200 OK with request object

### Deletion Order (Recommended)
```
1. Sonarr/Radarr DELETE ?deleteFiles=true  → Files deleted from disk
2. Shoko RemoveMissingFiles                 → Anime metadata cleaned
3. Jellyfin DELETE /Items/{id}              → Library entry removed
4. Jellyseerr DELETE /request/{id}          → Request cleared (optional)
```

**Why this order:**
- Sonarr/Radarr own the files → delete them first
- Shoko detects missing files → clean up anime metadata
- Jellyfin library entry becomes stale → remove it
- Jellyseerr auto-syncs but can be explicitly cleared

---

## SSE Events for Deletion

Multiple SSE events to track deletion progress in real-time:

```python
# 1. Deletion initiated - request removed from DB
{
    "event_type": "deletion_started",
    "deletion_log_id": 456,
    "title": "Interstellar (2014)",
    "services_to_sync": ["radarr", "jellyfin", "jellyseerr"]
}

# 2. Per-service progress updates
{
    "event_type": "deletion_progress",
    "deletion_log_id": 456,
    "service": "radarr",
    "status": "confirmed",
    "details": "API returned 200 OK",
    "timestamp": "2026-01-18T14:30:02Z"
}

# 3. Deletion fully verified
{
    "event_type": "deletion_completed",
    "deletion_log_id": 456,
    "all_verified": true,
    "completed_at": "2026-01-18T14:32:01Z"
}
```

---

## Verification Checklist

After all parts complete:

**Deletion Functionality:**
- [ ] Delete from dashboard → request removed from DB, all external services synced
- [ ] Bulk delete → multiple items deleted, all create DeletionLog entries
- [ ] External delete (Sonarr UI) → status-tracker detects and removes request
- [ ] External delete (Radarr UI) → status-tracker detects and removes request
- [ ] Deletion log shows all deletions with correct source
- [ ] Sync status shows which services succeeded/failed

**Security & Permissions:**
- [ ] Non-admin cannot see delete buttons
- [ ] Non-admin cannot access /deletion-logs page
- [ ] Non-admin API calls to delete endpoint return 403 Forbidden
- [ ] Admin IDs from .env are correctly validated

**Non-Regression (existing features still work):**
- [ ] New requests still tracked through full lifecycle
- [ ] SSE updates still work for state changes
- [ ] History page shows existing requests
- [ ] Detail page shows timeline
- [ ] Health endpoint returns healthy

**Re-request Flow:**
- [ ] After deletion, same media can be re-requested in Jellyseerr
- [ ] Re-request creates brand new request (not linked to deleted one)
- [ ] Jellyseerr shows previously-deleted media as "available for request"
