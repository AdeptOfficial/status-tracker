# Status Tracker: Detect Already-Available Media on Request

**Created:** 2026-01-18
**Status:** Open
**Component:** apps/status-tracker

## Problem

When a user requests media that already exists in the library (e.g., re-requesting after a deletion from status-tracker only), the request gets stuck in "approved" state.

**Why it happens:**
1. Jellyseerr sends `MEDIA_AUTO_APPROVED` webhook
2. Status tracker creates request with state "approved"
3. Radarr/Sonarr already has the file → no Grab webhook
4. Jellyfin already has the item → no ItemAdded webhook
5. Request stays "approved" forever

## Proposed Solution

Add a pre-hook check when receiving Jellyseerr webhook:

### Flow
```
Jellyseerr webhook received
    ↓
Extract TMDB ID from payload
    ↓
Check Radarr/Sonarr: Does movie/series exist with this TMDB ID?
    ├── No → Continue normal flow (state: approved, wait for Grab)
    └── Yes → Check if file exists (hasFile: true)
              ├── No → Continue normal flow (state: approved)
              └── Yes → Check Jellyfin for item
                        ├── Found → Set state: available, populate jellyfin_id
                        └── Not found → Trigger Jellyfin library scan, then check again
```

### Implementation Steps

1. **Add lookup methods to clients:**
   - `radarr_client.get_movie_by_tmdb(tmdb_id)` - already exists
   - `sonarr_client.get_series_by_tvdb(tvdb_id)` - already exists
   - `jellyfin_client.search_by_tmdb(tmdb_id)` - need to add

2. **Modify Jellyseerr plugin:**
   ```python
   # In handle_media_approved():
   async def handle_media_approved(payload, db):
       tmdb_id = payload.get("media", {}).get("tmdbId")
       media_type = payload.get("media", {}).get("mediaType")

       # Check if already available
       if media_type == "movie":
           radarr_movie = await radarr_client.get_movie_by_tmdb(tmdb_id)
           if radarr_movie and radarr_movie.get("hasFile"):
               # Movie already downloaded, check Jellyfin
               jellyfin_item = await jellyfin_client.search_by_tmdb(tmdb_id)
               if jellyfin_item:
                   # Already available - create request as available
                   request = create_request(state=RequestState.AVAILABLE)
                   request.jellyfin_id = jellyfin_item["Id"]
                   request.radarr_id = radarr_movie["id"]
                   return request

       # Normal flow - create as approved
       return create_request(state=RequestState.APPROVED)
   ```

3. **Add Jellyfin search method:**
   ```python
   # In app/clients/jellyfin.py
   async def search_by_provider_id(self, provider: str, id: str) -> Optional[dict]:
       """Search Jellyfin library by external provider ID (tmdb, tvdb, imdb)."""
       # GET /Items?AnyProviderIdEquals={provider}.{id}
       pass
   ```

## Files to Modify

- `app/clients/jellyfin.py` - Add `search_by_provider_id()` method
- `app/plugins/jellyseerr.py` - Add pre-check in `handle_media_approved()`

## Alternative Approaches

1. **Periodic sync job** - Scan library periodically and mark matching requests as available
   - Pro: Catches edge cases
   - Con: Delay, extra API calls

2. **Jellyseerr "available" webhook** - If Jellyseerr sends a different event for already-available media
   - Need to check Jellyseerr webhook docs

## Acceptance Criteria

- [ ] Re-requesting existing media immediately shows as "available"
- [ ] Request has correct `jellyfin_id` and `radarr_id`/`sonarr_id` populated
- [ ] No duplicate requests created
- [ ] Normal flow (new media) still works

## Related

- Current workaround: Manually update state in database
