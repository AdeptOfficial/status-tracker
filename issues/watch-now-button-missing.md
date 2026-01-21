# Status Tracker: "Watch Now" Button Missing for Webhook-Tracked Items

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker
**Priority:** Medium
**Feature:** Detail Page UI

## Problem

Items that reach "Ready to Watch" state via the normal webhook flow are missing the "Watch Now" button, while items synced from the Jellyfin library have it.

### Current Behavior

**JJK 0 (webhook-tracked):**
- State: Ready to Watch
- Shows: Only "Delete Media" button
- Missing: "Watch Now" button

**Interstellar (library-synced):**
- State: Ready to Watch
- Shows: "Watch Now" button AND "Delete Media" button

### Expected Behavior

All items in "Ready to Watch" state should show the "Watch Now" button that links to Jellyfin.

## Root Cause

The "Watch Now" button requires a `jellyfin_id` to generate the deep link URL:
```
{JELLYFIN_URL}/web/index.html#!/details?id={jellyfin_id}
```

**Library-synced items** get `jellyfin_id` populated during sync (fetched directly from Jellyfin).

**Webhook-tracked items** never receive a Jellyfin webhook with the item ID, so `jellyfin_id` remains null.

## Screenshots

See attached screenshots showing:
1. JJK 0 detail page - no Watch Now button
2. Interstellar detail page - has Watch Now button

## Proposed Fix

When transitioning to AVAILABLE state, query Jellyfin to find the item and populate `jellyfin_id`:

```python
# In state_machine.py or availability checker
if new_state == RequestState.AVAILABLE and not request.jellyfin_id:
    # Query Jellyfin by TMDB/TVDB ID
    jellyfin_item = await jellyfin_client.find_by_provider_id(
        provider="Tmdb" if request.media_type == "movie" else "Tvdb",
        provider_id=request.tmdb_id or request.tvdb_id
    )
    if jellyfin_item:
        request.jellyfin_id = jellyfin_item["Id"]
```

### Alternative: Jellyfin Webhook

If Jellyfin Webhook plugin is configured with "Item Added" events, the `jellyfin_id` could be populated from that webhook. But this requires:
1. Webhook plugin installed and configured
2. Correlation logic to match incoming items to tracked requests

## Acceptance Criteria

- [ ] Webhook-tracked items show "Watch Now" button when available
- [ ] `jellyfin_id` is populated when item reaches AVAILABLE state
- [ ] Deep link opens correct item in Jellyfin

## Related

- Similar to `library-sync-missing-ids.md` - both involve missing service IDs
- May need Jellyfin client method to search by provider ID
