# Feature: Add SYNCING_LIBRARY State

**Priority:** Medium
**Status:** Implemented
**Created:** 2026-01-21
**Implemented:** 2026-01-21

## Problem

After Shoko matches a file (`ANIME_MATCHING` state), there's a visibility gap before the item appears in Jellyfin (`AVAILABLE`). Users don't know if the system is:
- Waiting for Shoko TMDB/TVDB linking
- Waiting for Shokofin VFS regeneration
- Waiting for Jellyfin library scan

This applies to **both anime movies and anime shows**.

## Proposed Solution

Add a new state: `SYNCING_LIBRARY` (or `AWAITING_JELLYFIN`)

### State Flow

**Anime Movies:**
```
IMPORTING → ANIME_MATCHING → SYNCING_LIBRARY → AVAILABLE
              (Shoko FileMatched)  (Shoko MovieUpdated)  (Jellyfin found)
```

**Anime Shows:**
```
IMPORTING → ANIME_MATCHING → SYNCING_LIBRARY → AVAILABLE
              (Shoko FileMatched)  (Shoko EpisodeUpdated)  (Jellyfin found)
```

### Triggers

| Transition | Trigger | Media Type |
|------------|---------|------------|
| ANIME_MATCHING → SYNCING_LIBRARY | Shoko MovieUpdated "Added" | Movies |
| ANIME_MATCHING → SYNCING_LIBRARY | Shoko EpisodeUpdated with cross-refs | Shows |
| SYNCING_LIBRARY → AVAILABLE | Jellyfin item found by TMDB/TVDB | Both |

### Implementation Notes

1. **Add state to `RequestState` enum** in `app/models.py`
2. **Update `shoko.py` plugin:**
   - `handle_shoko_movie_available()` → transition to SYNCING_LIBRARY instead of triggering verification
   - Add similar handler for EpisodeUpdated events
3. **Update `jellyfin_verifier.py`:**
   - Check for SYNCING_LIBRARY state (in addition to ANIME_MATCHING)
   - Transition to AVAILABLE when found
4. **Update UI:**
   - Add SYNCING_LIBRARY to state display
   - Show appropriate message: "Syncing to Jellyfin library..."

### Timeline Display

```
Timeline:
✓ Approved          02:40 AM
✓ Found             02:40 AM
✓ Downloading       02:40 AM
✓ Downloaded        02:43 AM
✓ Importing         02:56 AM
✓ Anime Matching    02:56 AM  (Shoko matched to AniDB)
⟳ Syncing Library   02:56 AM  (Waiting for Jellyfin/Shokofin)
  Ready to Watch    --:-- --
```

### Files to Modify

- `app/models.py` - Add SYNCING_LIBRARY to RequestState enum
- `app/plugins/shoko.py` - Update MovieUpdated/EpisodeUpdated handlers
- `app/services/jellyfin_verifier.py` - Include SYNCING_LIBRARY in checks
- `app/templates/*.html` - Display new state appropriately

### Why Not More Granular States?

Considered `VFS_PENDING` → `LIBRARY_SCANNING` but:
- Harder to detect VFS regeneration (no clear event)
- Shokofin doesn't expose VFS status via API
- Single state is simpler and covers the user need

## Related

- Shokofin 6.0.2 "Inform library monitor before generating VFS" improvement
- TMDB exact match fix in `jellyfin.py`
- Jellyfin fallback checker in `jellyfin_verifier.py`
