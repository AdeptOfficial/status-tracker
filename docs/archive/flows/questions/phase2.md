# Phase 2 Questions (Radarr/Sonarr Grab)

## Open

### Q1: title_japanese / originalTitle

Database.md says we get `title_japanese` from Radarr/Sonarr `originalTitle`. But the captured webhook payloads don't show `originalTitle` field. Is it actually there? Need to verify with live capture.

**Status:** INVESTIGATE - Capture real webhook

---

## Answered

### Q2: Multiple Grab webhooks (TV individual episodes)

Sonarr may send multiple Grab webhooks if grabbing episodes individually (not season pack):

```
Grab 1: episodes=[S01E01, S01E02] → hash=ABC
Grab 2: episodes=[S01E03] → hash=DEF
Grab 3: episodes=[S01E04, S01E05] → hash=GHI
```

**Decision:** Per-episode tracking model. Each Grab webhook:
1. Updates Episode rows for those episodes
2. Sets `Episode.qbit_hash` to the downloadId
3. Sets `Episode.state` to GRABBING

Multiple episodes can share the same hash (multi-ep grab).

### Q3: How do we know total_episodes?

**Decision:** A - Call Sonarr API on first Grab to get full episode list for requested season(s). Create all Episode rows as PENDING, then update grabbed ones.

### Q4: State transition - INDEXED vs GRABBING

**Decision:** INDEXED state removed.
- Movies: `APPROVED → DOWNLOADING` (on Radarr Grab)
- TV: `APPROVED → GRABBING → DOWNLOADING` (GRABBING while episodes being grabbed)

### Q5: No matching request found

Grab webhook arrives but no active request with matching tmdb_id/tvdb_id. What do?

**Decision:** Set to FAILED state with error message. Log warning. (Edge case - shouldn't happen normally)

### Q6: Correlation edge case - multiple active requests same title

User requests Frieren S1, then immediately requests Frieren S2. Two active requests, same tvdb_id.

**Decision:** A - Most recent (created_at DESC). Accept this edge case - it's rare and the user can manually fix if needed.

### Q7: file_size - single or cumulative?

**Decision:** A - Sum of all grabs. For TV with individual episode grabs, accumulate total file_size across all Grab webhooks.

---

## Follow-up Questions

### Q8: Episode table schema

Q2 decision introduces "Episode rows" - this is a new table! Need to document schema:

```
Episode:
  id
  request_id (FK)
  season_number
  episode_number
  title?
  state (PENDING, GRABBING, DOWNLOADING, DOWNLOADED, IMPORTING, AVAILABLE)
  qbit_hash
  final_path
  shoko_file_id?
```

**Status:** NEEDS SCHEMA DOC - Update database.md with Episode table

### Q9: Sonarr API call failure

Q3 says call Sonarr API on first Grab. What if API call fails?
- A) Proceed without total_episodes (show "Grabbed 3 eps" not "3/12")
- B) Retry with backoff
- C) Fail the request

**Status:** NEEDS DECISION

### Q10: Movie qbit_hash storage

Q4 says Movies go APPROVED → DOWNLOADING on Radarr Grab. We also need to store the qbit_hash at this point. Confirm:
- Radarr Grab webhook → store `qbit_hash`, `radarr_id`, `quality`, etc → transition to DOWNLOADING

All in one operation?

**Status:** CONFIRM
