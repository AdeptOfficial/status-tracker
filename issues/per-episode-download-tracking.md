# Status Tracker: Per-Episode Download Tracking for TV/Anime

**Created:** 2026-01-18
**Status:** Open - Needs Planning
**Component:** apps/status-tracker
**Priority:** Medium
**Complexity:** High

## Problem

Currently, status-tracker treats TV shows and anime as a single request, even when downloading multiple episodes. The download progress shows aggregate data, but users can't see:

- Which specific episodes are downloading
- Individual episode progress
- Episode-level status (some done, some pending)

### Current Behavior
- One MediaRequest record per series request
- Single progress percentage (aggregate or first torrent)
- Timeline shows one "Downloading" event

### Desired Behavior
- Track each episode's download individually
- Show episode list with per-episode progress
- Display which episodes are complete vs in-progress

## Technical Challenges

### 1. Request Model Complexity

Current model is flat:
```
MediaRequest (1) ──── TimelineEvent (many)
```

Needs to become:
```
MediaRequest (1) ──┬── EpisodeRequest (many) ──── TimelineEvent (many)
                   └── TimelineEvent (many, for request-level events)
```

### 2. Multiple Torrents Per Request

A season request may result in:
- Single season pack torrent (1 torrent = 12 episodes)
- Multiple individual episode torrents (12 torrents)
- Mixed (batch + individual)

### 3. Webhook Correlation

Sonarr sends one grab webhook per torrent, not per episode. Need to:
- Parse episode info from release title
- Match torrent to correct episode(s)
- Handle season packs specially

### 4. qBittorrent Tracking

- Season packs: One torrent hash, multiple files
- Individual: One torrent hash per episode
- Need file-level progress for season packs

## Proposed Data Model

```python
class EpisodeRequest(Base):
    id: int
    media_request_id: int  # FK to MediaRequest
    season_number: int
    episode_number: int
    episode_title: str | None
    qbit_hash: str | None
    file_path: str | None
    status: str  # pending, downloading, importing, available
    progress: float
    created_at: datetime
    updated_at: datetime
```

## Implementation Phases

### Phase 1: Data Model (Foundation)
- Add EpisodeRequest table
- Migrate existing data
- Update schemas

### Phase 2: Episode Extraction
- Parse episode info from Sonarr grab webhook
- Create EpisodeRequest records
- Link to parent MediaRequest

### Phase 3: Progress Tracking
- Track per-episode progress from qBittorrent
- Handle season packs (file-level progress)
- Update EpisodeRequest status

### Phase 4: UI Updates
- Episode list component
- Per-episode progress bars
- Episode-level timeline

### Phase 5: Per-Episode Deletion
- Selective episode deletion (delete specific episodes, keep others)
- Cascade deletion (delete series = delete all episodes)
- Deletion sync per episode:
  - Remove episode from Sonarr (unmonitor or delete file)
  - Remove from qBittorrent if still downloading
  - Update Jellyfin library
- Episode-level deletion logs
- UI: Checkboxes for selective deletion, "Delete All" button

## Open Questions

1. How to handle season packs? Track as single "episode" or expand?
2. Should we show file sizes per episode?
3. How to handle anime absolute numbering vs season numbering?
4. Performance implications of polling many torrents?
5. For deletion: Should deleting one episode of a season pack delete the whole pack?
6. How to handle partial season deletions in Jellyseerr (mark as partially available)?

## Acceptance Criteria

- [ ] Episode list visible on detail page
- [ ] Individual episode progress shown
- [ ] Episode status (pending/downloading/done)
- [ ] Works with both season packs and individual episodes
- [ ] Anime episode numbering handled correctly
- [ ] Selective episode deletion works
- [ ] Cascade deletion (delete series) removes all episodes
- [ ] Deletion logs show episode-level details

## Notes

This is a significant architectural change. Recommend planning session before implementation. Consider backwards compatibility with existing requests.

### 2026-01-21: Release Type Detection

Need to implement detection for whether a grabbed release is:
- **Full season pack** (e.g., `[Group] Anime S01 (BD 1080p)` - one torrent, multiple episodes)
- **Per-episode release** (e.g., `[SubsPlease] Anime - 01 (1080p)` - one torrent per episode)

This affects how we track progress:
- Season packs: Need file-level progress within single torrent
- Per-episode: Track each torrent individually

Detection heuristics to consider:
- Parse release title for season indicators (`S01`, `Season 1`, `Complete`)
- Check torrent file count from qBittorrent API
- Use Sonarr's episode mapping from grab webhook

**Real-world example (2026-01-21):**
- **Horimiya**: Season pack (1 torrent = 13 episodes) → UI shows "S01E01" only
- **Link Click S3**: Per-episode (6 torrents = 6 episodes) → UI shows "S03E06" only

Both cases hide the true download scope from the user.

### 2026-01-21: Jellyfin Fallback Checker Needed for Anime Shows

**Problem observed:** Link Click S3 completed import (all 6 episodes processed by Shoko, TMDB linked) but status-tracker stays stuck at "Importing" - never transitions to "Available".

**Root cause:** Status-tracker only polls Jellyfin `/Sessions`, doesn't verify library item exists. Same issue we fixed for anime movies.

**Needed:** Implement Jellyfin fallback checker for anime TV shows:
- After Shoko reports file matched with cross-refs
- Query Jellyfin API to verify series/episodes exist in library
- Transition to "available" when confirmed

**Related:** Anime movie fallback checker implementation (see previous fix)

**Additional observation (same session):** Horimiya also stuck at "Importing" despite Jellyfin showing it in "Recently Added" with all 13 episodes. Confirms this is a systemic issue for anime TV shows, not just Link Click.

**Both cases observed:**
- Link Click S3 (6 eps) - stuck at Importing
- Horimiya S1 (13 eps) - stuck at Importing

Jellyfin detected both via Shokofin, but status-tracker never transitions to "Available".

**Missing IDs observed:**
- Both Link Click and Horimiya missing `jellyfin_id` in status-tracker database
- Without Jellyfin ID, fallback checker cannot verify item availability
- Need to query Jellyfin API to get series IDs after Shoko/Sonarr import completes

**Required for fallback checker:**
1. Query Jellyfin `/Items` API with series name or TVDB/TMDB ID (requires API key auth)
2. Store returned Jellyfin ID in database
3. Use ID to verify playability via `/Items/{id}/PlaybackInfo` or similar

**API Reference:** [Jellyfin API Overview](https://jmshrv.com/posts/jellyfin-api/) - Use `/Users/{userId}/Items?searchTerm=...&IncludeItemTypes=Series&Recursive=true&fields=ProviderIds` to get series with provider IDs for matching.

**Note:** Status-tracker already has Jellyfin API key configured - fallback checker should use existing client to query and store Jellyfin IDs automatically after import.
