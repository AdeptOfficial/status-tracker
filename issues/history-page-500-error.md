# Bug: /history Page 500 Internal Server Error

**Created:** 2026-01-22
**Status:** Fixed (awaiting deploy)
**Priority:** High
**Component:** API / Pages Router

## Problem

The `/history` page returns a 500 Internal Server Error with SQLAlchemy `MissingGreenlet` exception.

## Error

```
sqlalchemy.exc.MissingGreenlet: greenlet_spawn has not been called;
can't call await_only() here. Was IO attempted in an unexpected place?
```

## Root Cause

The `/history` endpoint query was missing `selectinload(MediaRequest.episodes)`.

When `history.html` includes `card.html`, the card template accesses `request.episodes` for per-episode display. Without eager loading, SQLAlchemy attempts a lazy load which fails in async context.

## Fix Applied

**File:** `app/routers/pages.py`

```python
# Before (broken)
stmt = select(MediaRequest)

# After (fixed)
stmt = select(MediaRequest).options(selectinload(MediaRequest.episodes))
```

## Related

- Per-episode tracking feature added `episodes` relationship to MediaRequest
- `card.html` displays episode progress which requires episodes to be loaded
- Other endpoints already had `selectinload`, but `/history` was missed
