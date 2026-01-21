# Status Tracker: Radarr Unable to Parse Anime Filenames

**Created:** 2026-01-19
**Status:** Open
**Component:** Radarr / Status Tracker Integration
**Priority:** Medium
**Feature:** State Machine / Import Tracking

## Problem

Radarr's completed download handler fails to import anime movie files when the release uses Japanese titles or non-standard naming conventions. The download completes successfully, but Radarr shows "Unable to parse file" and never sends the import webhook to status-tracker.

### Observed Behavior

1. Torrent downloads successfully to `/data/downloads/complete/`
2. Radarr's queue shows: "Downloaded - Waiting to Import"
3. Error message: "Unable to parse file"
4. No import webhook sent to status-tracker
5. Request stuck at `download_done` state

### Example

**Movie:** I Want to Eat Your Pancreas (2018)
**Downloaded filename:** `[YURI] Kimi no Suizou o Tabetai [BD1080p HEVC FLAC][Dual Audio] v4`
**Expected by Radarr:** `I Want to Eat Your Pancreas (2018)...`

Radarr cannot match the Japanese title "Kimi no Suizou o Tabetai" to the English movie title.

## Technical Context

### Radarr Parsing Logic

Radarr uses regex patterns to extract:
- Movie title
- Year
- Quality
- Release group

Anime releases often:
- Lead with Japanese (romaji) titles
- Include both Japanese and English titles
- Use non-standard bracketed formatting `[GROUP] Title (Japanese) [Quality]`
- Don't include year in filename

### Why This Breaks Import

1. Radarr can see the completed download in qBittorrent
2. Radarr tries to match filename to movies in database
3. Parser fails to extract recognizable title
4. Radarr marks as "Unable to parse" and waits for manual intervention
5. No automatic import = no webhook = status-tracker stuck

### Workaround

**Manual rename:**
```bash
mv "[YURI] Kimi no Suizou o Tabetai..." "I Want to Eat Your Pancreas (2018) 1080p BluRay"
```

After rename, Radarr auto-imports within 1 minute.

**Manual Import UI:**
- Radarr → Activity → Queue → Manual Import
- Select file and assign to correct movie

## Root Cause

Radarr's filename parser is optimized for Western releases. Anime releases from Nyaa.si often prioritize Japanese titles, which don't match Radarr's movie database (which uses English titles).

## Impact

- All anime movie downloads with Japanese-first titles fail to auto-import
- Status-tracker never reaches `importing` → `anime_matching` → `available`
- User must manually intervene for every anime movie

## Potential Solutions

### Option 1: Custom Radarr Parsing (Configuration)
Configure Radarr's "Custom Formats" or "Preferred Words" to recognize common anime release patterns. Limited effectiveness.

### Option 2: Pre-processing Script
Add a Radarr "Connect" script that renames files before import:
- Triggered on download complete
- Queries TMDB for English title using movie ID from Radarr
- Renames file to parseable format

### Option 3: Status-Tracker Polling Fallback
If stuck at `download_done` for X minutes:
- Query Radarr's queue API
- Detect "Unable to parse" state
- Alert user or trigger manual import flow

### Option 4: Different Indexer Strategy
Use anime-specific indexers that format filenames with English titles first:
- Some release groups prioritize English titles
- May sacrifice quality/availability

## Acceptance Criteria

- [ ] Anime movie downloads auto-import without manual intervention
- [ ] Status-tracker receives import webhooks for anime movies
- [ ] Solution handles common Nyaa.si release naming patterns

## Related Issues

- `radarr-tracking-queue-desync.md` - Different issue (queue tracking)
- This issue: Parser fails before queue tracking even matters

## References

- Radarr parsing code: `NzbDrone.Core/Parser/Parser.cs`
- Similar issue: https://github.com/Radarr/Radarr/issues/xxxx (anime parsing)
