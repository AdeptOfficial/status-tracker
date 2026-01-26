# Bug: Poster Not Loading on Detail Page

**Date:** 2026-01-25
**Severity:** Medium (UX issue)
**Status:** PENDING
**Type:** Bug

---

## Problem

The poster image is not loading on the detail page for "The Girl Who Leapt Through Time (2006)". Shows placeholder icon instead.

## Observations

- Request was just created via Jellyseerr
- poster_url may not be set or TMDB image URL is failing
- Other requests (Spirited Away) had working posters

## Possible Causes

1. Jellyseerr webhook doesn't include poster URL
2. TMDB image fetch failed
3. poster_url field is empty/null
4. TMDB URL format issue

## Files to Check

- `app/plugins/jellyseerr.py` - Check if poster_url is extracted from webhook
- `app/models.py` - Check poster_url field

## Debug

Check the request's poster_url value in database or API response.
