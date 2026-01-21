# Bug: SYNCING_LIBRARY State Not Triggering for Anime Movies

**Priority:** High
**Status:** Open
**Created:** 2026-01-21
**Category:** Bug

## Problem

The SYNCING_LIBRARY state implementation for anime movies is not working. The state transition from ANIME_MATCHING to SYNCING_LIBRARY never occurs because Shoko's `ShokoEvent:MovieUpdated` SignalR event does not fire for anime movies.

## Expected Flow

```
IMPORTING → ANIME_MATCHING → SYNCING_LIBRARY → AVAILABLE
              (FileMatched)    (MovieUpdated)    (Jellyfin)
```

## Actual Flow

```
IMPORTING → ANIME_MATCHING → AVAILABLE
              (FileMatched)    (fallback checker)
```

The fallback checker bypasses SYNCING_LIBRARY entirely.

## Root Cause

Shoko treats anime movies as **anime series** with movie episodes, not as TMDB movies. The `movie` SignalR feed is for non-anime TMDB movies only.

Evidence from Shoko logs:
```
Updated WATCHED stats for SERIES Seishun Buta Yarou wa Yumemiru Shoujo no Yume o Minai
```

The anime movie "Rascal Does Not Dream of a Dreaming Girl" is categorized as an anime series, so `ShokoEvent:MovieUpdated` never fires.

## Test Evidence

- Movie: Rascal Does Not Dream of a Dreaming Girl (2019)
- TMDB ID: 572154
- SignalR hub connected with feeds: `shoko,file,movie,episode`
- `ShokoEvent:MovieUpdated` handler registered but never called
- No `[MOVIE UPDATED]` logs appeared
- Movie went directly from `anime_matching → available via jellyfin-fallback`

## Resolution

**Action:** Reverting code changes to restore original working flow.

The SYNCING_LIBRARY state implementation will be reverted. The original flow (FileMatched → fallback verification → AVAILABLE) was working correctly before the update.

## Future Considerations

If SYNCING_LIBRARY state is desired in the future:
1. **Use SeriesUpdated event:** Subscribe to anime series events instead of MovieUpdated
2. **Trigger via fallback:** Add SYNCING_LIBRARY transition in fallback checker before AVAILABLE
3. **Redesign flow:** See `design-separate-anime-movie-show-flows.md` for architectural considerations

## Files Affected

- `app/clients/shoko.py` - MovieUpdated handler
- `app/plugins/shoko.py` - handle_shoko_movie_available()
- `app/services/jellyfin_verifier.py` - fallback checker logic

## Related

- Original working flow used FileMatched → direct verification
- SYNCING_LIBRARY state was added for UX visibility but broke the flow
