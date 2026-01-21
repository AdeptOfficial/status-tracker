# Status Tracker: Missing Poster Image on Detail Page

**Created:** 2026-01-18
**Status:** Resolved
**Resolved:** 2026-01-18
**Component:** apps/status-tracker
**Priority:** Medium

## Problem

The request detail page shows a placeholder icon instead of the media poster image. The poster area displays the Status Tracker logo/hashtag icon rather than the actual movie or TV show artwork.

### Observed Behavior
- Detail page shows placeholder icon in poster area
- No poster image loaded from any source

### Expected Behavior
- Display poster artwork for the requested media
- Fallback to placeholder only if no poster available

## Technical Context

### Potential Poster Sources

1. **Jellyseerr** - Has poster URLs in webhook payload
2. **TMDB API** - Can fetch via tmdb_id (requires API key)
3. **Jellyfin** - Can proxy image if media exists in library
4. **Sonarr/Radarr** - Store poster paths in their APIs

### Recommended Approach

Store poster URL when processing Jellyseerr webhook. Jellyseerr includes `image` field:

```json
{
  "notification_type": "MEDIA_AUTO_APPROVED",
  "media": {
    "tmdbId": 120089,
    "image": "/path/to/poster.jpg"  // Jellyseerr provides this
  }
}
```

Construct full URL: `https://image.tmdb.org/t/p/w500{image}`

### Relevant Files
- `app/plugins/jellyseerr.py` - Webhook processing (add poster extraction)
- `app/models.py` - MediaRequest model (add poster_url field)
- `app/schemas.py` - Response schemas
- `app/templates/detail.html` - Display poster
- `app/templates/components/card.html` - Card display

## Implementation Steps

1. Add `poster_url` column to MediaRequest model
2. Extract poster from Jellyseerr webhook payload
3. Store TMDB image URL in database
4. Update detail.html to display poster
5. Update card.html for index page

## Acceptance Criteria

- [ ] Poster displays on detail page
- [ ] Poster displays on request cards (index page)
- [ ] Graceful fallback for missing posters
- [x] No external API calls needed (use Jellyseerr data)

## Resolution

**Fix:** Changed `media.get("image")` to `payload.get("image")` in `app/plugins/jellyseerr.py`.

Jellyseerr sends the full TMDB poster URL at the top level of the webhook payload, not inside the `media` object:
```json
{
  "image": "https://image.tmdb.org/t/p/w600_and_h900_bestv2/xxx.jpg",
  "media": { ... }
}
```

The fix reads the URL directly from `payload.get("image")` - no URL construction needed.
