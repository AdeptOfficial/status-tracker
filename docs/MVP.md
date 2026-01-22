# Status Tracker MVP

**Goal:** Track media requests from Jellyseerr through to availability in Jellyfin, with correct state updates across all 4 media paths.

---

## What "Done" Looks Like

A user requests media in Jellyseerr. Status-tracker:

1. **Creates a request card** showing title, poster, requester
2. **Updates state automatically** as webhooks arrive (no stuck requests)
3. **Shows correct state** for each phase (Approved → Grabbing → Downloading → Importing → Available)
4. **Handles all 4 paths** correctly:
   - Regular Movie
   - Regular TV
   - Anime Movie
   - Anime TV
5. **Marks as Available** when actually playable in Jellyfin

---

## The 4 Flows (Must All Work)

### Flow 1: Regular Movie
```
Jellyseerr → Radarr Grab → qBit Download → Radarr Import → Jellyfin (TMDB lookup) → AVAILABLE
```

### Flow 2: Regular TV
```
Jellyseerr → Sonarr Grab → qBit Download → Sonarr Import → Jellyfin (TVDB lookup) → AVAILABLE
```

### Flow 3: Anime Movie
```
Jellyseerr → Radarr Grab → qBit Download → Radarr Import → Shoko Match → Jellyfin → AVAILABLE
```

### Flow 4: Anime TV
```
Jellyseerr → Sonarr Grab → qBit Download → Sonarr Import → Shoko Match → Jellyfin → AVAILABLE
```

---

## MVP Scope

### In Scope (Must Have)

| Feature | Description |
|---------|-------------|
| Request creation | Jellyseerr webhook creates request with poster, title, IDs |
| State tracking | Correct state shown at each phase (9 states) |
| Per-episode tracking | TV shows track individual episodes with Episode table |
| Correlation | Webhooks match to correct request (not old/completed ones) |
| All 4 paths | Movie, TV, Anime Movie, Anime TV all work |
| Available detection | Request marked AVAILABLE when in Jellyfin |
| Fallback checker | Stuck requests eventually get verified |
| Download progress | qBit polling shows % for movies, episode counts for TV |
| Basic UI | List of requests with current state |

### Out of Scope (Post-MVP)

| Feature | Why Defer |
|---------|-----------|
| Live SSE updates | Nice-to-have, can refresh for now |
| Deletion sync | Separate feature, not blocking |
| Library sync button | Separate feature |
| Multi-user support | Single admin for MVP |
| Japanese titles | Requires TMDB API call, not in webhooks |

---

## State Machine (MVP)

```
REQUESTED → APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE
                                                                  │
                                                           (anime only)
                                                                  ↓
                                                           ANIME_MATCHING
                                                                  ↓
                                                              AVAILABLE
```

**9 States:**
- `REQUESTED` - User requested, awaiting admin approval
- `APPROVED` - Approved, waiting for Radarr/Sonarr to grab
- `GRABBING` - Grabbed from indexer, qBit queued/starting
- `DOWNLOADING` - qBit actively downloading
- `DOWNLOADED` - qBit complete, waiting for Radarr/Sonarr import
- `IMPORTING` - Radarr/Sonarr importing to library
- `ANIME_MATCHING` - Anime only, waiting for Shoko to match
- `AVAILABLE` - In Jellyfin, ready to watch
- `FAILED` - Error occurred

**Notes:**
- Movies: Same flow, GRABBING shows "Grabbed" briefly
- TV: GRABBING shows "Grabbed 3/12 eps", DOWNLOADING shows "5 downloading, 3 downloaded"
- DOWNLOADED helps debug stuck imports (qBit done but arr hasn't imported yet)

---

## Acceptance Criteria

### Phase 1: Request Creation
- [ ] Jellyseerr `MEDIA_AUTO_APPROVED` creates request
- [ ] Jellyseerr `MEDIA_PENDING` creates request with REQUESTED state
- [ ] Poster URL extracted from `image` field
- [ ] Title and year parsed correctly
- [ ] Duplicate request (same media, already AVAILABLE) shows "Already Available"
- [ ] Duplicate request (same media, in progress) returns existing request

### Phase 2: Indexer Grab
- [ ] Radarr `Grab` webhook updates request to GRABBING
- [ ] Sonarr `Grab` webhook updates request to GRABBING
- [ ] `qbit_hash` stored for download correlation (Movie: on MediaRequest, TV: on Episode rows)
- [ ] `is_anime` detected from `movie.tags` or `series.type`
- [ ] TV: Create Episode rows from `episodes[]` array in webhook
- [ ] Correct request matched (not old AVAILABLE one)

### Phase 3: Download Progress
- [ ] Request transitions to DOWNLOADING when qBit starts
- [ ] Request transitions to DOWNLOADED when qBit completes (100% or seeding)
- [ ] Movies: Show progress % in UI
- [ ] TV: Show episode counts ("3 downloaded, 5 downloading, 4 queued")

### Phase 4: Import
- [ ] Radarr `Download` webhook updates to IMPORTING
- [ ] Sonarr `Download` webhook updates to IMPORTING
- [ ] `final_path` stored for Shoko correlation
- [ ] `is_anime` determined from path

### Phase 5: Verification
- [ ] Regular Movie: Jellyfin TMDB lookup → AVAILABLE
- [ ] Regular TV: Jellyfin TVDB lookup → AVAILABLE
- [ ] Anime Movie: Shoko FileMatched → AVAILABLE (or ANIME_MATCHING → fallback)
- [ ] Anime TV: Shoko FileMatched → AVAILABLE (or ANIME_MATCHING → fallback)
- [ ] Fallback checker catches stuck requests

---

## Test Scenarios

### Happy Path Tests

| # | Test | Expected Result |
|---|------|-----------------|
| 1 | Request regular movie | APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE |
| 2 | Request regular TV (1 season) | Same, with Episode rows showing per-ep progress |
| 3 | Request anime movie | Same + ANIME_MATCHING after IMPORTING |
| 4 | Request anime TV (1 season) | Same + ANIME_MATCHING, per-episode tracking |

### Edge Case Tests

| # | Test | Expected Result |
|---|------|-----------------|
| 5 | Re-request already available media | Shows "Already Available" |
| 6 | Re-request media still in progress | Returns existing request |
| 7 | Shoko doesn't match (wrong AniDB ID) | ANIME_MATCHING → fallback finds in Jellyfin → AVAILABLE |
| 8 | Jellyfin webhook fails | Fallback checker marks AVAILABLE |

---

## Webhook Investigation Findings (2026-01-21)

Captured real webhooks from test requests. Key confirmations:

| Finding | Impact |
|---------|--------|
| `downloadId` = qBit hash | Correlation works: 40-char uppercase hex matches qBit |
| Sonarr `episodes[]` has full data | Episode rows created from webhook, no API call needed |
| Sonarr `series.type == "anime"` | `is_anime` detected at Phase 2, not Phase 4 |
| Radarr `movie.tags` has `"anime"` | Same - anime detection at grab time |
| Jellyseerr `extra[].value = "1"` | Requested seasons format confirmed |
| Specials = movies | No special `media_type`, treated as movies by Radarr |

**Still need to capture:** Import webhooks, Shoko notifications

---

## Bug Fixes Required

| Bug | File | Fix |
|-----|------|-----|
| Poster URL wrong field | `jellyseerr.py` | Use `image` not `extra["Poster 500x750"]` |
| Correlation matches old request | `correlator.py` | Add state filtering (exclude AVAILABLE/DELETED) |
| TV fallback missing | `jellyfin_verifier.py` | Remove `media_type == "movie"` filter |
| Year not extracted | `jellyseerr.py` | Parse from subject string |
| Anime ID mismatch | `jellyfin_verifier.py` | Dual search (Movie + Series by TMDB) |

---

## Database Schema (MVP)

```
MediaRequest:
  # Core
  id, title, year, media_type, state, is_anime

  # Correlation
  jellyseerr_id, tmdb_id, tvdb_id, imdb_id
  qbit_hash (movies only), final_path (movies only)

  # Service IDs
  radarr_id, sonarr_id, jellyfin_id

  # Display
  poster_url, requested_by, quality, requested_seasons (TV)

  # Progress (movies)
  download_progress

  # Timestamps
  created_at, updated_at, available_at

Episode (TV only):
  id, request_id (FK)
  season_number, episode_number, episode_title
  state (per-episode: PENDING→GRABBING→DOWNLOADING→DOWNLOADED→IMPORTING→AVAILABLE)
  qbit_hash, final_path
  shoko_file_id (anime), jellyfin_id
  created_at, updated_at
```

**Key insight from webhook investigation:** Sonarr Grab includes full `episodes[]` array with titles - no API call needed to create Episode rows!

---

## Definition of Done

MVP is complete when:

1. **All 4 test scenarios pass** (regular movie, regular TV, anime movie, anime TV)
2. **No requests get stuck** indefinitely (fallback catches them)
3. **Correct request is updated** (correlation fix works)
4. **UI shows accurate state** for each request
5. **Bugs listed above are fixed**

---

## Post-MVP Roadmap

1. **SSE Live Updates** - No refresh needed for state changes
2. **Download Progress** - Show % and ETA during download
3. **GRABBING State** - Show episode grab progress for TV
4. **Deletion Sync** - Delete from all services when removed
5. **Library Sync** - Button to sync existing library items
