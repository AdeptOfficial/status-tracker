# Status Tracker: Bulk Media Sync from Library

**Created:** 2026-01-18
**Updated:** 2026-01-18
**Status:** Phase 1 Complete
**Component:** apps/status-tracker
**Priority:** Medium

## Problem

When media is added to the library through non-traditional methods (direct file copy, manual import, existing library before status-tracker was set up), there's no way to populate the status dashboard with these items.

Currently, the only way to add items to the dashboard is:
1. Request through Jellyseerr → triggers webhook flow
2. Manually insert into database (admin/developer only)

This creates a gap where existing library content isn't visible in the status tracker.

---

## Solution: Two-Phase Sync

### Why Two Phases?

**Critical insight:** We must use Jellyfin as the source of truth for AVAILABLE status. Marking something AVAILABLE when Jellyfin doesn't see it creates false positives on the dashboard.

| Phase | Source of Truth | Creates State | Status |
|-------|-----------------|---------------|--------|
| Phase 1 | Jellyfin | AVAILABLE | **In Progress** |
| Phase 2 | Jellyseerr | REQUESTED/APPROVED/etc | Future |

---

## Phase 1: Available Content Sync (Current Focus)

### Flow

```
Admin clicks "Sync Library"
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 1: Fetch from Jellyfin (Source of Truth)              │
│  GET /Items?Recursive=true&IncludeItemTypes=Movie,Series    │
│       &fields=ProviderIds,Path,Overview                     │
│  → Returns ALL library items with TMDB/TVDB/IMDB IDs        │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 2: Fetch from status-tracker DB                       │
│  SELECT tmdb_id, tvdb_id FROM requests                      │
│  → Build set of already-tracked IDs                         │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 3: Filter Jellyfin items                              │
│  Remove items where tmdb_id OR tvdb_id already in DB        │
│  → Remaining = items to sync                                │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 4: Enrich with Radarr/Sonarr IDs (Required)           │
│  Fetch ALL from Radarr: GET /api/v3/movie                   │
│  Fetch ALL from Sonarr: GET /api/v3/series                  │
│  Build lookup dicts: {tmdb_id: radarr_id}, {tvdb_id: ...}   │
│  Match in-memory (no per-item API calls)                    │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────────────────────────────────┐
│  Step 5: Create AVAILABLE entries                           │
│  For each untracked Jellyfin item:                          │
│    - Create MediaRequest with state=AVAILABLE               │
│    - Populate: jellyfin_id, tmdb_id, tvdb_id                │
│    - Populate: radarr_id OR sonarr_id (from Step 4)         │
│    - Set requested_by = "Library Sync"                      │
│    - Add timeline event: "Synced from library"              │
└─────────────────────────────────────────────────────────────┘
    │
    ▼
Return SyncResult {added, skipped, errors}
```

### API Calls (Optimized)

| Service | Calls | Purpose |
|---------|-------|---------|
| Jellyfin | 1-2 | Fetch all library items with ProviderIds |
| Radarr | 1 | Fetch all movies for ID correlation |
| Sonarr | 1 | Fetch all series for ID correlation |
| Database | 1 | Fetch existing tmdb_id/tvdb_id set |

**Total: 4-5 API calls** regardless of library size. All bulk queries, local filtering.

### Correlation ID Population

| Field | Source | Notes |
|-------|--------|-------|
| `jellyfin_id` | Jellyfin | Primary key from source of truth |
| `tmdb_id` | Jellyfin ProviderIds | Movies use this |
| `tvdb_id` | Jellyfin ProviderIds | TV shows use this |
| `imdb_id` | Jellyfin ProviderIds | Bonus, stored in poster_url or separate field |
| `radarr_id` | Radarr bulk fetch | Matched by tmdb_id |
| `sonarr_id` | Sonarr bulk fetch | Matched by tvdb_id |
| `jellyseerr_id` | NULL | Not applicable - items weren't requested via Jellyseerr |
| `shoko_series_id` | Future | Phase 1 skips Shoko enrichment |

### Files to Create/Modify

| File | Action |
|------|--------|
| `app/clients/jellyfin.py` | Add `get_all_items()` method |
| `app/clients/sonarr.py` | Add `get_all_series()` method |
| `app/clients/radarr.py` | Add `get_all_movies()` method |
| `app/services/library_sync.py` | **New** - LibrarySyncService |
| `app/routers/api.py` | Add `POST /api/admin/sync/library` |
| `app/templates/status.html` | Add sync button (admin only) |
| `app/schemas.py` | Add SyncResult schema |

### Endpoint

```
POST /api/admin/sync/library
Authorization: X-Jellyfin-Token (admin only)

Response:
{
  "total_scanned": 127,
  "added": 42,
  "skipped": 85,
  "errors": 0,
  "error_details": []
}
```

### UI Location

Add to existing Status page (`/status`) for admin users:

```
┌─────────────────────────────────────────────────────────────┐
│ Library Sync                                    [Admin Only] │
├─────────────────────────────────────────────────────────────┤
│ Sync existing media from Jellyfin to the status dashboard.  │
│ Only syncs items that are actually available in Jellyfin.   │
│                                                              │
│ [Sync Available Content]                                     │
│                                                              │
│ Last sync: Never                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Phase 2: Pending Content Sync (Future)

**Status:** Planned (not in current scope)

### Concept

Sync pending/in-progress content from Jellyseerr that hasn't reached Jellyfin yet.

### Flow (High-Level)

1. Fetch all requests from Jellyseerr API
2. Filter out items already in Jellyfin (handled by Phase 1)
3. Filter out items already in status-tracker DB
4. Determine current state by checking Sonarr/Radarr/qBittorrent
5. Create entries with appropriate state (REQUESTED, APPROVED, DOWNLOADING, etc.)

### Challenges

- State detection requires checking multiple services in order
- Timing issues if content is mid-import
- qBittorrent hash correlation for active downloads

### Deferred Because

- Phase 1 handles the primary use case (existing library not tracked)
- Pending content will naturally appear when webhooks fire
- State detection complexity adds significant implementation time

---

## Edge Cases

1. **Duplicate detection** - Match by TMDB/TVDB ID, not title (titles vary)
2. **Anime movies** - Matched via Radarr (tmdb_id), Shoko enrichment deferred
3. **Missing IDs** - Create entry with available IDs, log warning for missing
4. **Large libraries** - Batch creates, show progress via SSE
5. **TV Shows** - Create one entry per series (not per episode)

---

## Security

- Admin-only endpoint via `require_admin_user` dependency
- Audit logging for sync operations
- No credentials read or displayed

---

## Related

- `configs/dev/services/status-tracker/roadmap.md` - Feature roadmap
- `issues/improvements/media-deletion-resync-checklist.md` - Related sync topic
