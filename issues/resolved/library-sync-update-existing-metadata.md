# Feature Request: Library Sync - Update Existing Media Metadata

**Created:** 2026-01-19
**Status:** Open
**Priority:** Medium
**Type:** Enhancement

## Problem Statement

Current library sync (`/api/admin/sync/library`) only adds NEW items from Jellyfin. It skips existing entries even when they're missing critical metadata like `jellyfin_id`.

**Current behavior:**
```python
# app/services/library_sync.py:185-190
if jellyfin_id and jellyfin_id in existing_jellyfin_ids:
    return "skipped"
if tmdb_id and tmdb_id in existing_tmdb_ids:
    return "skipped"  # ← Skips even if jellyfin_id is NULL
```

**Consequences:**
- Media added before library sync existed have incomplete metadata
- Media where Jellyfin webhook was missed stay in AVAILABLE state without `jellyfin_id`
- Deletion sync can't target Jellyfin (shows "not_needed" status)
- Deep links to Jellyfin don't work

**Current state example:**
```
ID 10: COLORFUL STAGE! The Movie (2025) - TMDB: 1322752
  Status: AVAILABLE
  Jellyfin ID: NULL ← Missing!
```

## Proposed Solution

Enhance library sync to UPDATE existing entries when metadata is missing or stale.

### Option A: Two-Phase Sync (Recommended)

Add a second pass that updates existing entries with missing fields:

```python
async def sync_available_content(self, update_existing=True) -> SyncResult:
    # Phase 1: Add new items (current behavior)
    ...

    # Phase 2: Update existing items with missing metadata
    if update_existing:
        await self._update_missing_metadata(jellyfin_items)
```

**Update logic:**
- Match by TMDB ID (movies) or TVDB ID (TV shows)
- Only update NULL fields (don't overwrite existing data)
- Fields to update:
  - `jellyfin_id` (critical for deletion sync)
  - `poster_url` (if NULL and Jellyfin has one)
  - `year` (if NULL and Jellyfin has one)
  - `radarr_id` / `sonarr_id` (from enrichment lookups)

### Option B: Separate Endpoint

Create `/api/admin/sync/update-metadata` for explicit metadata updates:

```python
@router.post("/admin/sync/update-metadata")
async def update_existing_metadata(...):
    """
    Update missing metadata for existing AVAILABLE items.

    Matches by TMDB/TVDB ID and fills in:
    - jellyfin_id
    - poster_url
    - radarr_id / sonarr_id
    """
```

**Pros:**
- Clear separation of concerns (add vs. update)
- Can be run on-demand for specific scenarios
- Won't slow down initial sync

**Cons:**
- Requires two API calls for full sync
- Users need to know both endpoints exist

### Option C: Smart Skip Logic

Only skip if the entry has ALL required fields populated:

```python
# Skip only if we have complete metadata
has_complete_metadata = all([
    jellyfin_id,
    radarr_id if media_type == MOVIE else True,
    sonarr_id if media_type == TV else True,
])

if has_complete_metadata and jellyfin_id in existing_jellyfin_ids:
    return "skipped"
```

**Pros:**
- Simplest implementation
- No API changes needed

**Cons:**
- Less control over when updates happen
- Might update data users don't want changed

## Use Cases

1. **Backfill missing Jellyfin IDs** - Current situation with 3 AVAILABLE movies
2. **Recover from missed webhooks** - Jellyfin ItemAdded webhook lost → no jellyfin_id stored
3. **Migration scenarios** - Jellyfin library rebuilt with new IDs
4. **Enrichment after feature additions** - When new fields added to schema, backfill from Jellyfin

## Current Workaround

Manual database update using Jellyfin API:

```bash
# Find Jellyfin ID by TMDB ID
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker python -c "
import httpx, os
jellyfin_key = os.environ.get('JELLYFIN_API_KEY', '')
resp = httpx.get(
    'http://jellyfin:8096/Items',
    headers={'X-Emby-Token': jellyfin_key},
    params={'AnyProviderIdEquals': 'tmdb.1322752'}
)
print(resp.json()['Items'][0]['Id'] if resp.json()['Items'] else 'Not found')
"'

# Update database
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker python -c "
import sqlite3
conn = sqlite3.connect('/config/tracker.db')
cursor = conn.cursor()
cursor.execute('UPDATE requests SET jellyfin_id = ? WHERE id = ?', ('abc123', 10))
conn.commit()
"'
```

## Implementation Considerations

### Safety

- **Never overwrite existing non-NULL values** (preserve user corrections)
- **Log all updates** with before/after values
- **Transaction safety** - rollback on errors
- **Dry-run mode** - preview changes before applying

### Performance

- Batch updates in single transaction
- Use existing Jellyfin API calls (already fetches all items)
- Add optional `--update-existing` flag to avoid slowdown when not needed

### Timeline Events

Should metadata updates create timeline events?

**Option 1:** Yes, for transparency
```
"Library sync updated Jellyfin ID: NULL → abc123def456"
```

**Option 2:** No, silent updates
- Less clutter in timeline
- Metadata fixes aren't user-facing state changes

## Affected Components

- `app/services/library_sync.py` - Core sync logic
- `app/routers/api.py` - API endpoint (if new endpoint created)
- `app/schemas.py` - SyncResult response (add `updated` field)
- Tests - Add test cases for update scenarios

## Success Metrics

After implementation:
- All AVAILABLE items have `jellyfin_id` populated
- Deletion sync can target Jellyfin successfully
- Deep links work for all library content
- Zero manual database updates needed

## Related Issues

- Current gap: 3 movies missing `jellyfin_id` (JJK 0, Rascal, COLORFUL STAGE)
- Library Sync feature added 2026-01-17 (Phase 1 only)
- See: `apps/status-tracker/DIARY.md` entry "2026-01-18: Library Sync feature"

## Recommendation

**Implement Option A (Two-Phase Sync)** with:
- Default `update_existing=True` behavior
- Optional query param `?update_existing=false` to disable
- Log updates to console (not timeline)
- Transaction safety with rollback on errors

This provides the best balance of automation and control while maintaining backward compatibility.
