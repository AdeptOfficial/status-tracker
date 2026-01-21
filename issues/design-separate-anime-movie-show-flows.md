# Design: Separate Monitoring Flows for Anime Movies vs Anime Shows

**Priority:** High
**Status:** Open
**Created:** 2026-01-21
**Category:** Architecture / Design

## Finding

Anime movies and anime TV shows need to be monitored differently in status-tracker. Shoko Server treats them fundamentally differently, which affects what SignalR events are available.

## How Shoko Categorizes Media

### Anime Movies
- Categorized as **anime series** with a single movie episode
- Linked to AniDB anime entries (not TMDB movies)
- Example: "Rascal Does Not Dream of a Dreaming Girl" → AniDB series "Seishun Buta Yarou wa Yumemiru Shoujo no Yume o Minai"
- `ShokoEvent:MovieUpdated` does NOT fire (this is for non-anime TMDB movies)
- `ShokoEvent:FileMatched` fires when file is matched to AniDB

### Anime TV Shows
- Categorized as **anime series** with multiple episodes
- Linked to AniDB anime entries
- `ShokoEvent:EpisodeUpdated` may fire when episodes are linked
- `ShokoEvent:FileMatched` fires for each episode file

### Non-Anime Movies (TMDB)
- Categorized as standalone movies
- Linked directly to TMDB
- `ShokoEvent:MovieUpdated` fires for these

## Current Problem

The SYNCING_LIBRARY state implementation assumed:
- Anime movies would trigger `MovieUpdated` → They don't
- We could use a unified flow for all anime → We can't

## Proposed Solution

### Option 1: Detect Media Type Early

```
IF media_type == movie AND is_anime:
    Use anime movie flow (FileMatched → series-based detection)
ELIF media_type == tv AND is_anime:
    Use anime show flow (FileMatched/EpisodeUpdated)
ELIF media_type == movie:
    Use standard movie flow (MovieUpdated)
```

### Option 2: Use FileMatched as Primary Trigger

For all anime (movies and shows):
1. `FileMatched` → `ANIME_MATCHING`
2. Check if file has cross-references (TMDB/TVDB)
3. If yes → `SYNCING_LIBRARY`
4. Verify in Jellyfin → `AVAILABLE`

### Option 3: Abandon SYNCING_LIBRARY for Anime

Keep the original flow:
1. `FileMatched` → `ANIME_MATCHING`
2. Fallback checker polls Jellyfin
3. When found → `AVAILABLE`

This loses visibility into the "syncing to Jellyfin" phase but is simpler.

## Key Differences to Handle

| Aspect | Anime Movie | Anime Show | Non-Anime Movie |
|--------|-------------|------------|-----------------|
| Shoko category | Series | Series | Movie |
| SignalR event | FileMatched | FileMatched/EpisodeUpdated | MovieUpdated |
| Cross-ref type | AniDB → TMDB | AniDB → TVDB | TMDB direct |
| Jellyfin lookup | TMDB ID | TVDB ID | TMDB ID |
| Episode count | 1 | Multiple | 1 |

## Files Affected

- `app/clients/shoko.py` - Event handlers
- `app/plugins/shoko.py` - Flow logic
- `app/services/jellyfin_verifier.py` - Verification logic
- `app/models.py` - Possibly need anime_type field

## Next Steps

1. Test SNAFU (anime TV show) to understand its event flow
2. Document actual SignalR events received for anime shows
3. Design unified but type-aware monitoring system
4. Consider adding `anime_type` field to MediaRequest model

## Related

- `bug-syncing-library-not-triggering.md`
- Shoko SignalR documentation (if available)
- Shokofin VFS behavior
