# Issue: Radarr/Sonarr Rejecting All Releases

**Date:** 2026-01-25
**Status:** DEV Interstellar coverage repaired; historical anime/TV validation open
**Priority:** High

## October 20 repair and movie flow proof

Added/tested free public Knaben id10 with movies tag and synced Radarr. Interstellar
query returned68 Knaben results,33 approved. A normal approved4.21GiB1080p release
was selected to fit available storage instead of the preferred33.26GiB remux.
No force/profile override. Download, Radarr import, Jellyfin discovery and tracker23
Available then occurred automatically. File is readable and hardlinked; playback
and fresh-folder modes not yet proved. This is manual selection followed by
normal automatic flow, not proof of unattended selection under current capacity.

Aligned Prowlarr and new internal-only Byparr helper direct egress. Full1337x test
passed/backoff cleared; torrent VPN/kill switch preserved. No production change.
See newest DIARY and homeserver notes/2026-10-20-dev-knaben-validation.json.
The following sections are historical pre-change evidence; January profile claims
remain hypotheses rather than the proven cause of this movie failure.

## October 20 follow-up: search infrastructure diagnosis

1337x is enabled but in Cloudflare failure backoff. Its solver shares the correct
tag but uses a different public exit from Prowlarr. Both temporary aligned and
existing solver browser fetches reached the real site; full Prowlarr cookie replay
still needs testing. No live routing/indexer settings changed. Recommended adding
Knaben for general coverage after its public API returned20 seeded Interstellar
results from DEV. Not added or tested through Radarr yet. See homeserver issue
`issues/bugs/cloudflare-indexers-unavailable.md` and newest diaries.

## October 20 live reproduction: wrong content from search

Fresh Interstellar2014 re-request: Jellyseerr152 → tracker23 Approved → Radarr108
monitored. Automatic MoviesSearch742302 completed at15:38:16 UTC with no grab.
Interactive query returned13 Nyaa.si (Prowlarr) results and0 approved; all reported
Unable to parse release. Inspected samples are unrelated anime titled Interstellar
Wanderer/Interstellar Journey, not TMDB157336. No qBittorrent download, Radarr file
or Jellyfin item exists for this request. Tracker correctly remains Approved.

Do not infer a quality/custom-format failure from the January hypothesis below:
current evidence establishes missing matching movie results. Restore general-movie
indexer coverage, confirm correct title/year, then observe an ordinary automatic
grab; do not force unrelated releases or weaken profiles to make a test pass.
No indexer configurations/credentials were read or changed during this check.

The existing empty film folder (1000:1000,0775) was reused, so fresh-directory
permissions remain untested. Current226-test build is unchanged. This check
proves re-request creation/correlation only, not download/import/playback.

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
