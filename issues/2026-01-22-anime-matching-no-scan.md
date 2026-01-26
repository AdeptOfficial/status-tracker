# Issue: ANIME_MATCHING State Doesn't Trigger Jellyfin Scan

**Date:** 2026-01-22
**Severity:** High
**Status:** Open

---

## Problem

The fallback checker triggers Jellyfin library scans for requests in `IMPORTING` state but NOT for `ANIME_MATCHING` state. This leaves anime requests stuck.

## Code Location

`app/services/jellyfin_verifier.py:440-445`

```python
# Current code only triggers scan for IMPORTING
needs_scan = any(r.state == RequestState.IMPORTING for r in stuck_requests)
if needs_scan:
    await jellyfin_client.trigger_library_scan()
```

## Fix Needed

Also trigger scans for ANIME_MATCHING:

```python
needs_scan = any(r.state in (RequestState.IMPORTING, RequestState.ANIME_MATCHING) for r in stuck_requests)
```

## Impact

- Anime TV/Movie requests get stuck at ANIME_MATCHING indefinitely
- Requires manual Jellyfin library scan to proceed
- Breaks the "fully automatic" flow for anime content

## Affected Requests

- My Teen Romantic Comedy SNAFU - stuck at anime_matching
