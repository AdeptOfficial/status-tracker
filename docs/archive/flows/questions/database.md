# Database Schema Questions

## Open

### Q6: DOWNLOAD_DONE state - why needed?

Diagram shows DOWNLOAD_DONE between DOWNLOADING and IMPORTING. But sometimes Sonarr/Radarr stop monitoring the hash and require manual imports.

**Status:** INVESTIGATE - Why does this happen? Is DOWNLOAD_DONE useful for debugging these cases?

**Current Decision:** Keep DOWNLOAD_DONE state for debugging stuck imports.

---

## Answered

### Q1: qbit_hashes array - appending

**Decision:** Per-episode model changes this. Instead of `qbit_hashes[]` on MediaRequest:
- Each `Episode` row has `qbit_hash: str`
- Multiple Episode rows can share the same hash (multi-ep grab)
- Movies still use `MediaRequest.qbit_hash` (single string, no Episode rows)

### Q2: GRABBING → DOWNLOADING transition

**Decision:** Transition when ALL episodes for the request are grabbed (all Episode rows have state >= GRABBING). This happens on the last Sonarr Grab webhook for the season, or immediately for season packs.

### Q3: Three episode counters - how to increment?

**Decision:** Per-episode model. Count Episode rows by state instead of storing counters:

```python
grabbed_count = count(Episode.state >= GRABBING)
downloaded_count = count(Episode.state >= DOWNLOADED)
imported_count = count(Episode.state >= IMPORTING)
```

### Q4: shoko_file_id - single or multiple?

**Decision:** Per-episode. `Episode.shoko_file_id` - each episode can have its own Shoko file ID.

### Q5: final_path - TV shows

**Decision:** Per-episode. `Episode.final_path` - each episode has its own import path.

### Q7: Movie state flow

**Decision:** Movies skip GRABBING:
```
APPROVED → DOWNLOADING (on Radarr Grab webhook)
DOWNLOADING → DOWNLOAD_DONE (on qBit completion)
DOWNLOAD_DONE → IMPORTING (on Radarr Import webhook)
IMPORTING → AVAILABLE (on Jellyfin verification)
```

---

## Follow-up Questions

### Q8: Episode table - full schema needed

**Decision:** Final Episode schema:

```
Episode:
  id
  request_id (FK → MediaRequest)
  season_number
  episode_number
  episode_title         ← Yes, get from Sonarr API
  state                 ← PENDING, GRABBING, DOWNLOADING, DOWNLOADED, IMPORTING, AVAILABLE
  qbit_hash
  final_path
  shoko_file_id
  jellyfin_id           ← Yes, for per-episode verification
  created_at
  updated_at
```

**Notes:**
- `episode_title`: Yes - get from Sonarr API when creating Episode rows
- `download_progress`: No - derive from qBit hash lookup at runtime (not stored)
- `jellyfin_id`: Yes - needed for per-episode Jellyfin verification

### Q9: MediaRequest state vs Episode states

MediaRequest has a `state`. Episodes also have `state`. How do they relate?

**Decision:** Episodes only have individual states during download phase. Import and beyond are batch operations.

**Display logic:**
| State | Display |
|-------|---------|
| GRABBING | "Grabbed 3/12 eps" |
| DOWNLOADING | "3 downloading, 5 downloaded" |
| IMPORTING | "Importing..." |
| AVAILABLE | "Available" |

- **GRABBING/DOWNLOADING/DOWNLOADED:** Episodes tracked individually, show counts
- **IMPORTING → AVAILABLE:** Batch operation, simple status text

MediaRequest.state = aggregate (lowest state among episodes).

### Q10: Hash collision across requests

Same qbit_hash could appear in:
- Episode row for Request A (old, AVAILABLE)
- Episode row for Request B (new, active)

**Decision:** When looking up by hash, exclude AVAILABLE/DELETED requests:

```python
episodes = db.query(Episode).filter(
    Episode.qbit_hash == completed_hash,
    Episode.request.state.not_in([AVAILABLE, DELETED])
).all()
```

This ensures old completed requests are ignored.
