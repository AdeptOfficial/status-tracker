# Phase 1: Request Creation

**Source:** Jellyseerr
**Trigger:** Webhook `MEDIA_PENDING` or `MEDIA_AUTO_APPROVED`
**State Transition:** `[None]` → `REQUESTED` or `APPROVED`

---

## Webhook Payloads

### Movie Request

```json
{
  "notification_type": "MEDIA_AUTO_APPROVED",
  "subject": "Chainsaw Man: The Movie - Reze Arc (2025)",
  "image": "https://image.tmdb.org/t/p/w600_and_h900_bestv2/...",
  "media": {
    "media_type": "movie",
    "tmdbId": "1386807",
    "tvdbId": null,
    "status": "PENDING"
  },
  "request": {
    "request_id": "14",
    "requestedBy_username": "adept"
  },
  "extra": []
}
```

### TV Series Request (Verified 2026-01-21)

```json
{
  "notification_type": "MEDIA_AUTO_APPROVED",
  "subject": "Insomniacs After School (2023)",
  "image": "https://image.tmdb.org/t/p/w600_and_h900_bestv2/qChtK3uuCc5L5CpSeBpVV4MFRHD.jpg",
  "media": {
    "media_type": "tv",
    "tmdbId": "155440",
    "tvdbId": "414562",
    "status": "PENDING"
  },
  "request": {
    "request_id": "66",
    "requestedBy_username": "adept"
  },
  "extra": [
    {"name": "Requested Seasons", "value": "1"}
  ]
}
```

---

## Field Extraction

| Field | Source | Required | Notes |
|-------|--------|----------|-------|
| `title` | `subject` (parsed) | YES | Remove year suffix |
| `year` | `subject` (parsed) | YES | Extract from "(2023)" |
| `media_type` | `media.media_type` | YES | `"movie"` or `"tv"` |
| `tmdb_id` | `media.tmdbId` | YES | Present for both movies and TV |
| `tvdb_id` | `media.tvdbId` | TV only | Present for TV shows |
| `jellyseerr_id` | `request.request_id` | YES | For Jellyseerr correlation |
| `poster_url` | `image` | YES | **Direct field, NOT in extra array** |
| `requested_by` | `request.requestedBy_username` | NO | For UI display |
| `requested_seasons` | `extra[name="Requested Seasons"].value` | TV only | Which season(s) requested |

### Important Notes

- `extra["Requested Seasons"]` contains **which season** was requested (e.g., `"1"`), **NOT** the total episode count
- Episode count must come from Sonarr's Grab webhook (`episodes[]` array)
- Poster URL is in the `image` field directly, not nested in `extra`

---

## Flow

```
Jellyseerr webhook arrives
         │
         ▼
┌─────────────────────────────────┐
│ Parse payload                    │
│ - title, year from subject       │
│ - poster from `image` field      │
│ - tmdb_id, tvdb_id, jellyseerr_id│
└─────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────┐
│ Check: Already AVAILABLE?        │
│ find_by_any(include AVAILABLE)   │
└─────────────────────────────────┘
         │
    ┌────┴────┐
    │         │
   YES        NO
    │         │
    ▼         ▼
  Return    ┌─────────────────────────┐
  {         │ Check: Active duplicate? │
   already_ │ find_by_any(exclude      │
   available│   AVAILABLE, DELETED)    │
   =true    └─────────────────────────┘
  }              │
            ┌────┴────┐
            │         │
           YES        NO
            │         │
            ▼         ▼
         Return    Create new
         existing  MediaRequest
         request   state=APPROVED/REQUESTED
```

### Duplicate Handling

| Scenario | Action | UI Result |
|----------|--------|-----------|
| Request exists, state=AVAILABLE | Return with `already_available=true` | Show "Watch Now" + "Delete" (admin) |
| Request exists, state=active | Return existing request | Show current progress |
| No duplicate | Create new request | Show new card |

---

## Parsing Logic

### Title and Year Extraction

```python
import re

def parse_title_and_year(subject: str) -> tuple[str, int | None]:
    """
    Parse "Show Name (2023)" into ("Show Name", 2023)
    """
    match = re.match(r"^(.+?)\s*\((\d{4})\)$", subject)
    if match:
        return match.group(1).strip(), int(match.group(2))
    return subject, None

# Examples:
# "Insomniacs After School (2023)" → ("Insomniacs After School", 2023)
# "Frieren: Beyond Journey's End (2023)" → ("Frieren: Beyond Journey's End", 2023)
# "Some Show" → ("Some Show", None)
```

### Poster URL Extraction

```python
def extract_poster_url(payload: dict) -> str | None:
    """
    Extract poster URL - use `image` field directly.
    """
    # Primary: Direct image field (verified working 2026-01-21)
    if image := payload.get("image"):
        return image

    # Fallback: Check extra array (legacy, may not exist)
    for item in payload.get("extra", []):
        if "poster" in item.get("name", "").lower():
            return item.get("value")

    return None
```

---

## is_anime Detection

At Phase 1, we have limited info:

| Media Type | Detection | Reliability |
|------------|-----------|-------------|
| TV | Sonarr anime category (if configured) | Medium |
| Movie | Cannot detect | None |

**Decision:** Set `is_anime=null` at Phase 1. Final determination at Phase 4 via `final_path`.

For TV, we *could* check if Sonarr's root folder is anime, but this requires API call. Defer to Phase 2/4.

---

## State Transitions

```
[None] → REQUESTED   (if notification_type == "MEDIA_PENDING")
[None] → APPROVED    (if notification_type == "MEDIA_AUTO_APPROVED")
```

**MEDIA_PENDING:** Non-admin user request, waiting for approval.
**MEDIA_AUTO_APPROVED:** Admin request, auto-approved.

---

## Data Stored After Phase 1

```python
MediaRequest(
    id=14,
    title="Chainsaw Man: The Movie - Reze Arc",
    year=2025,
    media_type="movie",
    state="approved",  # or "requested"
    tmdb_id=1386807,
    tvdb_id=None,
    jellyseerr_id=14,
    poster_url="https://image.tmdb.org/t/p/...",
    requested_by="adept",
    requested_seasons="1",  # TV only
    is_anime=None,  # Determined at Phase 4
    # NOT YET SET:
    qbit_hash=None,
    radarr_id=None,
    sonarr_id=None,
    quality=None,
    indexer=None,
    final_path=None,
)
```

---

## Bugs in Current Implementation

### Bug: Poster URL Lookup

**Current code:**
```python
for item in extra:
    if item.get("name") == "Poster 500x750":  # Wrong!
        poster_url = item.get("value")
```

**Fix:**
```python
poster_url = payload.get("image")  # Direct field
```

### Bug: No State Filtering on Duplicate Check

**Current code:**
```python
request = await correlator.find_by_any(
    db,
    jellyseerr_id=jellyseerr_id,
    tmdb_id=tmdb_id,
    tvdb_id=tvdb_id,
)  # May return AVAILABLE request!
```

**Fix:**
```python
# First check if already available (for UI)
available = await correlator.find_by_any(
    db, jellyseerr_id=jellyseerr_id, tmdb_id=tmdb_id, tvdb_id=tvdb_id,
    include_states=[RequestState.AVAILABLE],
)
if available:
    return {"request": available, "already_available": True}

# Then check for active duplicate
active = await correlator.find_by_any(
    db, jellyseerr_id=jellyseerr_id, tmdb_id=tmdb_id, tvdb_id=tvdb_id,
    exclude_states=[RequestState.AVAILABLE, RequestState.DELETED],
)
```

### Bug: Year Not Extracted

**Current code:**
```python
title=payload.get("subject", "Unknown Title")  # Includes year
```

**Fix:**
```python
title, year = parse_title_and_year(payload.get("subject", ""))
```

---

## Testing Checklist

- [ ] Movie request (auto-approved)
- [ ] TV request (auto-approved)
- [ ] TV request with multiple seasons - does `extra["Requested Seasons"]` show `"1, 2"` or separate entries?
- [ ] Non-admin request (MEDIA_PENDING flow)
- [ ] Duplicate request when original is AVAILABLE
- [ ] Duplicate request when original is still in progress
- [ ] Poster URL extraction from `image` field

---

## Next Phase

→ [Phase 2: Indexer Grab](phase-2-indexer-grab.md)
