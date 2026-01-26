# Feature: Display Original/Japanese Title

**Created:** 2026-01-25
**Status:** Proposed
**Priority:** Medium
**Category:** UI/UX, Debugging

## Problem

When anime isn't found by indexers, it's often because:
- Indexers use Japanese/romaji titles (e.g., "Dareka no Manazashi")
- Jellyseerr/TMDB uses English titles (e.g., "Someone's Gaze")

Users have no visibility into this mismatch from the status-tracker dashboard.

## Proposed Solution

Display the original title (Japanese/native language) alongside the English title on:
1. Request cards on the index page
2. Detail page header
3. Timeline events (optional)

## Data Source

TMDB provides `original_title` field which contains the native language title.

**Options:**
1. **Jellyseerr webhook** - Check if `original_title` is included in payload
2. **TMDB API** - Fetch directly using `tmdb_id` (requires API key)
3. **Radarr/Sonarr** - They may have the original title in their payloads

## Implementation

### Database
```python
# app/models.py - Add to MediaRequest
original_title: Mapped[str | None] = mapped_column(String, nullable=True)
```

### Plugin Changes
```python
# app/plugins/jellyseerr.py - Extract from webhook or fetch from TMDB
original_title = media.get("originalTitle") or media.get("original_title")
```

### UI Changes
```html
<!-- app/templates/detail.html -->
<h1>{{ media_request.title }}</h1>
{% if media_request.original_title and media_request.original_title != media_request.title %}
    <p class="text-gray-400 text-sm">{{ media_request.original_title }}</p>
{% endif %}
```

### Card Component
```html
<!-- app/templates/components/card.html -->
<span class="text-xs text-gray-500">{{ request.original_title }}</span>
```

## Acceptance Criteria

- [ ] `original_title` stored in database when available
- [ ] Original title displayed on detail page (if different from English title)
- [ ] Original title displayed on cards (smaller text, optional toggle)
- [ ] Works for both movies and TV shows
- [ ] Graceful handling when original title is not available

## Alternatives Considered

1. **Manual title search** - Let users search Prowlarr manually (current workaround)
2. **Link to TMDB** - Just link to TMDB page where user can see alternate titles
3. **Full alias support** - Store all known aliases (overkill for this use case)

## Related

- Helps diagnose indexer search failures
- Useful for anime which commonly has JP/EN title mismatches
