# Phase 1 Questions (Jellyseerr Request)

## Open

### Q2: media_type "special"

Schema has `movie | tv | special`. Does Jellyseerr ever send "special"? Or detect later?

**Status:** INVESTIGATE

---

## Answered

### Q1: Year extraction

`subject` is "Frieren (2023)". Options:
- A) Parse out year at Phase 1, store separately ✓
- B) Store whole string, parse when displaying
- C) Store both (title with year + year field)

**Decision:** A - Parse and store `title` and `year` as separate fields.

### Q3: Duplicate check

Before CREATE, check for existing active request with same `tmdb_id`/`tvdb_id`?

**Decision:**
- If exists in AVAILABLE → return `already_available=true` (UI shows "Watch Now")
- If exists in ACTIVE state → return existing request, **UI redirects to existing request**

### Q4: Initial state

Two webhook types:
- `MEDIA_PENDING` → state = REQUESTED (needs approval)
- `MEDIA_AUTO_APPROVED` → state = APPROVED (auto-approved)

**Decision:** Confirmed correct.

### Q5: requested_seasons (TV)

In `extra[name="Requested Seasons"].value`. Grab at Phase 1?

**Decision:** Yes, store at Phase 1. Used to filter which episodes to track.

---

## Follow-up Questions

### Q6: API response for duplicate check

Q3 decision says "return existing request" or "already_available=true". What does the actual API response look like?

```python
# Option A: Different response shapes
{"status": "already_available", "jellyfin_id": "abc123"}
{"status": "in_progress", "request_id": 42}

# Option B: Same shape, flag indicates status
{"request_id": 42, "already_available": true, "created": false}
{"request_id": 42, "already_available": false, "created": false}  # existing in-progress
{"request_id": 99, "already_available": false, "created": true}   # new request
```

**Status:** NEEDS DECISION
