# Bug: Jellyseerr MEDIA_AVAILABLE Handler Incomplete

**Created:** 2026-01-22
**Status:** Fixed (awaiting deploy)
**Priority:** High
**Component:** Plugins / Jellyseerr

## Problem

When Jellyseerr sends a `MEDIA_AVAILABLE` webhook, the handler only transitions the request state to AVAILABLE but doesn't:
1. Mark episodes as AVAILABLE
2. Look up and set `jellyfin_id` (required for Watch button)

## Symptoms

- Request shows "Ready to Watch" but episodes show "Matching"
- "Watch Now" button missing (requires `jellyfin_id`)
- Episode progress shows "0/12 ready" when request is AVAILABLE

## Root Cause

The Jellyseerr MEDIA_AVAILABLE handler was minimal - just a state transition. The fallback checker (`jellyfin_verifier.py`) does the full job but only runs for "stuck" requests (>5 min old).

When Jellyseerr webhook fires quickly (before fallback), it wins the race but doesn't complete all the work.

## Fix Applied

**File:** `app/plugins/jellyseerr.py`

Updated MEDIA_AVAILABLE handler to:
1. Mark all episodes as AVAILABLE
2. Look up Jellyfin item by TVDB/TMDB ID
3. Set `jellyfin_id` and `available_at`

```python
if notification_type == "MEDIA_AVAILABLE":
    if request:
        # Mark all episodes as available
        for episode in request.episodes:
            episode.state = EpisodeState.AVAILABLE

        # Look up Jellyfin item for Watch button
        jellyfin_item = await jellyfin_client.find_item_by_tvdb(...)
        if jellyfin_item:
            request.jellyfin_id = jellyfin_item.get("Id")
            request.available_at = datetime.utcnow()

        await state_machine.transition(...)
```

## Related

- Bocchi the Rock test case (request ID 7)
- Lycoris Recoil worked correctly (fallback checker path)
