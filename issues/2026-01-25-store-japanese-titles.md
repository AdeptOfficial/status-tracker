# Feature: Store Japanese/Alternative Titles for Better Matching

**Date:** 2026-01-25
**Severity:** Medium (affects anime matching)
**Status:** PENDING
**Type:** Feature request

---

## Problem

Anime releases often use different title variations:
- English: "Spirited Away"
- Japanese: "千と千尋の神隠し"
- Romaji: "Sen to Chihiro no Kamikakushi"

Currently, status-tracker only stores the English title from Jellyseerr. This can cause:
1. Failed correlation when release uses Japanese title
2. Harder to manually match in Shoko
3. Missed SignalR events if Shoko uses different title format

## Proposed Solution

Store alternative titles in MediaRequest model:

```python
class MediaRequest(Base):
    title = Column(String)           # Primary (English)
    title_japanese = Column(String)  # Japanese (kanji/hiragana)
    title_romaji = Column(String)    # Romanized Japanese
    alternate_titles = Column(JSON)  # Array of all known titles
```

## Data Sources

1. **TMDB** - Has alternative titles endpoint: `/movie/{id}/alternative_titles`
2. **AniDB** (via Shoko) - Has Japanese titles
3. **Jellyseerr** - May include original title in request

## Implementation Steps

1. Add title columns to MediaRequest model
2. When creating request, fetch alternative titles from TMDB
3. For anime, also query Shoko/AniDB for Japanese title
4. Update correlator to check all title variants
5. Display primary + Japanese title in UI

## Use Cases

1. **Correlation:** Match releases regardless of title language
2. **UI:** Show "Spirited Away (千と千尋の神隠し)" for clarity
3. **Search:** Users can search by any title variant

## Example

| Field | Value |
|-------|-------|
| title | Spirited Away |
| title_japanese | 千と千尋の神隠し |
| title_romaji | Sen to Chihiro no Kamikakushi |
| alternate_titles | ["Spirited Away", "Sen to Chihiro no Kamikakushi", "千と千尋の神隠し", "El viaje de Chihiro"] |
