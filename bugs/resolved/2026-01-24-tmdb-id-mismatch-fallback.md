# Status-Tracker: Fallback TMDB ID Mismatch

**Status:** Open, unverified against the current build (moved from homeserver 2026-10-20)
**Discovered:** 2026-01-24
**Priority:** High
**Affected Services:** status-tracker
**LXC:** 220 (media-dev)

## Summary

The Jellyfin fallback checker fails to find anime movies when Radarr/Jellyseerr use a different TMDB ID than Shokofin/AniDB.

## Root Cause

When Shokofin matches an anime movie via AniDB, it may map to a different TMDB entry than the one Radarr/Jellyseerr originally used. The fallback checker (`jellyfin_verifier.py`) searches Jellyfin by TMDB ID, which fails when IDs don't match.

## Example: 5 Centimeters per Second

```
Radarr/Jellyseerr TMDB ID: 38142
Shokofin/AniDB TMDB ID:    1359916

Both are valid TMDB entries for the same anime movie.
```

The fallback searches for `tmdb.38142` but Jellyfin has it indexed as `tmdb.1359916`, causing the search to fail.

## Current Workaround

Manually transition request to AVAILABLE via Python script:
```python
req.state = RequestState.AVAILABLE
```

## Proposed Fix

Modify `jellyfin_verifier.py` fallback to:
1. First try TMDB ID search (current behavior)
2. If not found, fall back to title + year match
3. Accept fuzzy title matching for anime (removes punctuation, handles "The Movie" variants)

## Code Location

- `app/services/jellyfin_verifier.py` (this repo)
- Function: `_search_jellyfin_for_item()` or equivalent

## Related

- `bugs/resolved/2026-10-17-movie-provider-mismatch.md`: the same title (TMDB 38142 vs 1359916) was repaired on DEV as a metadata mismatch on 2026-10-17. Confirm whether the verifier's title/year fallback proposed above was also implemented before closing this.
- Testing session: 2026-01-24
- Test case: "5 Centimeters per Second" add flow

## Triage 2026-10-20

**Verdict:** Resolved by later work. **Status:** Resolved (triage, repo evidence; no live check in this pass).
`jellyfin_verifier.py` matches alternate titles (`parse_alternate_titles`) and verifies by imported path rather than TMDB id alone; the original title was repaired in `bugs/resolved/2026-10-17-movie-provider-mismatch.md`.
