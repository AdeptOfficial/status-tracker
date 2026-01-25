# Issue: Radarr/Sonarr Rejecting All Releases

**Date:** 2026-01-25
**Status:** Investigation Complete - Arr Configuration Issue
**Priority:** High

## Summary

Radarr and Sonarr are finding releases on indexers but rejecting ALL of them, preventing automatic downloads. This affects both anime and non-anime content.

## Evidence

### Radarr (Kase-san and Morning Glories)
```
Found 21 releases for movie 81 (0 approved, 21 rejected)
Common rejections: ['Unable to parse release', 'Unknown Movie. Unable to match to correct movie using release title.']
```

### Sonarr (SPY X FAMILY)
```
DownloadDecisionMaker: Processing 442 releases
EpisodeSearchService: Completed search for 12 episodes. 0 reports downloaded.
```

## Root Cause Analysis

1. **NOT a status-tracker issue** - Status-tracker correctly:
   - Receives Jellyseerr webhooks (creates requests)
   - Syncs alternate titles to Radarr (confirmed working)
   - Would receive Grab webhooks if arr apps grabbed anything

2. **Arr quality profile configuration** - Likely causes:
   - Quality profile requiring specific codecs/resolutions not available
   - Custom formats rejecting release groups
   - Anime custom formats misconfigured
   - Minimum quality requirements too strict

3. **Alternate titles working but not parsing** - Even with Japanese titles added to Radarr, the releases are being rejected at the quality profile level, not the parsing level.

## Status-Tracker Changes Made

These changes are WORKING correctly:

1. **Radarr client methods** (`app/clients/radarr.py`):
   - `lookup_movie()` - lookup movie from TMDB via Radarr
   - `add_alternate_titles()` - add alternate titles for release matching
   - `search_and_grab_anime()` - search releases and grab best match
   - `trigger_search()` - trigger automatic search

2. **Anime title sync service** (`app/services/anime_title_sync.py`):
   - Detects anime movies by genre/tags
   - Syncs alternate titles from TMDB
   - Stores titles in database for Shoko matching

3. **API endpoint** (`app/routers/api.py`):
   - `POST /api/requests/{id}/sync-titles` - manual title sync trigger

4. **Automatic sync** (`app/plugins/jellyseerr.py`):
   - Background task syncs titles when movie requests are created

## Required Fix (Outside Status-Tracker)

Check Radarr/Sonarr quality profiles and custom formats:

1. **Radarr**:
   - Settings > Profiles > Quality Profiles
   - Settings > Custom Formats
   - Movies > {Movie} > Interactive Search (to see rejection reasons)

2. **Sonarr**:
   - Settings > Profiles > Quality Profiles
   - Settings > Profiles > Release Profiles
   - Series > {Series} > Interactive Search (to see rejection reasons)

## Verification Steps

1. In Radarr, go to Movies > Kase-san and Morning Glories > Interactive Search
2. Click on any release to see the rejection reasons
3. Adjust quality profile or custom formats based on the rejection reasons
4. Same process for Sonarr with SPY X FAMILY
