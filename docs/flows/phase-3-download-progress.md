# Phase 3: Download Progress

**Source:** qBittorrent API polling
**Trigger:** Adaptive polling (5s active, 30s idle)
**State Transitions:**
- Movies: `DOWNLOADING` → `DOWNLOADED`
- TV Episodes: `GRABBING` → `DOWNLOADING` → `DOWNLOADED`

---

## Overview

Unlike other phases, this isn't webhook-driven. We poll qBittorrent's API to track download progress and update episode states.

**Key difference from other phases:** Per-episode tracking for TV. Each Episode row has its own state, and multiple episodes can share a qbit_hash (multi-ep grabs).

---

## Data Source

### qBittorrent API

```
GET /api/v2/torrents/info
```

### Response

```json
[
  {
    "hash": "abc123def456789...",
    "name": "Frieren.S01E01-02.1080p.WEB-DL",
    "progress": 0.75,
    "state": "downloading",
    "eta": 1800,
    "dlspeed": 5000000,
    "size": 4500000000,
    "completed": 3375000000
  }
]
```

### qBittorrent States

| State | Meaning | Our Interpretation |
|-------|---------|-------------------|
| `downloading` | Active download | DOWNLOADING |
| `stalledDL` | No peers, waiting | DOWNLOADING |
| `pausedDL` | Paused by user | DOWNLOADING |
| `queuedDL` | Waiting in queue | GRABBING |
| `checkingDL` | Verifying data | DOWNLOADING |
| `uploading` | Complete, seeding | DOWNLOADED |
| `stalledUP` | Complete, no peers | DOWNLOADED |
| `pausedUP` | Complete, paused | DOWNLOADED |
| `forcedUP` | Force seeding | DOWNLOADED |

---

## Flow

### Movies (Simple)

```
qBit poll
    │
    ▼
┌─────────────────────────────────┐
│ Find request by qbit_hash       │
│ (exclude AVAILABLE, DELETED)    │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Update progress on MediaRequest │
│ Check completion                │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ progress >= 100% OR seeding?    │
└─────────────────────────────────┘
    │
   YES → state = DOWNLOADED
    │
   NO  → stay DOWNLOADING
```

### TV Shows (Per-Episode)

```
qBit poll
    │
    ▼
┌─────────────────────────────────┐
│ Get all unique hashes from      │
│ Episode table (active requests) │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ For each torrent in qBit:       │
│ - Find Episodes with this hash  │
│ - Update Episode states         │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ For each Episode:               │
│ - qBit queued? → GRABBING       │
│ - qBit downloading? → DOWNLOADING│
│ - qBit complete? → DOWNLOADED   │
└─────────────────────────────────┘
    │
    ▼
┌─────────────────────────────────┐
│ Recalculate MediaRequest state  │
│ from Episode states             │
└─────────────────────────────────┘
```

---

## State Transitions

### Episode States (TV)

```
GRABBING → DOWNLOADING    (qBit starts downloading)
DOWNLOADING → DOWNLOADED  (qBit reaches 100% OR seeding state)
```

### Completion Detection

```python
def is_download_complete(torrent) -> bool:
    """Check if torrent download is complete."""
    return (
        torrent.progress >= 1.0 or
        torrent.state in ("uploading", "stalledUP", "forcedUP", "pausedUP")
    )

def is_downloading(torrent) -> bool:
    """Check if torrent is actively downloading."""
    return torrent.state in (
        "downloading", "stalledDL", "pausedDL", "forcedDL", "metaDL", "checkingDL"
    )

def is_queued(torrent) -> bool:
    """Check if torrent is queued, not yet started."""
    return torrent.state == "queuedDL"
```

---

## Correlation Logic

### Movies

```python
request = await db.query(MediaRequest).filter(
    MediaRequest.qbit_hash == torrent_hash,
    MediaRequest.state.not_in([RequestState.AVAILABLE, RequestState.DELETED])
).first()
```

### TV Episodes

```python
episodes = await db.query(Episode).join(MediaRequest).filter(
    Episode.qbit_hash == torrent_hash,
    MediaRequest.state.not_in([RequestState.AVAILABLE, RequestState.DELETED])
).all()
```

**Note:** Multiple episodes may share the same hash (multi-ep grab). All episodes with that hash get updated together.

---

## Progress Display

### Movies

```
"Downloading... 68%"
```

### TV Shows

**List view:**
```
Frieren S1 • DOWNLOADING • 3 downloaded, 5 downloading, 4 queued
```

**Detail view:**
```
Episode 1  "The Journey's End"     ✓ Downloaded
Episode 2  "It Didn't Have to Be"  ✓ Downloaded
Episode 3  "Killing Magic"         ⬇ Downloading 68%
Episode 4  "The Mage's Secret"     ⬇ Downloading 68%
Episode 5  "Phantoms"              ⏳ Queued
...
```

### Count Calculation

```python
def get_download_counts(episodes: list[Episode]) -> dict:
    """Get episode counts by download state."""
    return {
        "downloaded": sum(1 for e in episodes if e.state == EpisodeState.DOWNLOADED),
        "downloading": sum(1 for e in episodes if e.state == EpisodeState.DOWNLOADING),
        "queued": sum(1 for e in episodes if e.state == EpisodeState.GRABBING),
    }
```

---

## Adaptive Polling

Poll frequency depends on active downloads:

```python
async def get_poll_interval(db: AsyncSession) -> int:
    """Return poll interval based on active downloads."""
    active_count = await count_episodes_in_state(
        db,
        states=[EpisodeState.GRABBING, EpisodeState.DOWNLOADING]
    )

    # Also check movies
    active_count += await count_requests_in_state(
        db,
        states=[RequestState.DOWNLOADING],
        media_type="movie"
    )

    return 5 if active_count > 0 else 30
```

### Polling Loop

```python
async def poll_qbittorrent():
    while True:
        interval = await get_poll_interval(db)

        if interval == 5:  # Active downloads
            torrents = await qbit_client.get_torrents()
            await update_download_progress(db, torrents)

        await asyncio.sleep(interval)
```

---

## Update Logic

### Movies

```python
async def update_movie_progress(request: MediaRequest, torrent, db):
    """Update movie download progress."""
    old_progress = request.download_progress or 0
    new_progress = int(torrent.progress * 100)

    # Update progress
    request.download_progress = new_progress

    # Check completion
    if is_download_complete(torrent) and request.state == RequestState.DOWNLOADING:
        await transition_state(request, RequestState.DOWNLOADED, db)
        logger.info(f"Movie download complete: {request.title}")
```

### TV Episodes

```python
async def update_episode_progress(episodes: list[Episode], torrent, db):
    """Update progress for all episodes sharing this hash."""
    for episode in episodes:
        # Determine new state
        if is_download_complete(torrent):
            new_state = EpisodeState.DOWNLOADED
        elif is_downloading(torrent):
            new_state = EpisodeState.DOWNLOADING
        elif is_queued(torrent):
            new_state = EpisodeState.GRABBING
        else:
            continue

        # Update if changed
        if episode.state != new_state:
            episode.state = new_state
            logger.debug(f"Episode {episode.episode_number} -> {new_state}")

    # Recalculate parent request state
    request = episodes[0].request
    request.state = calculate_aggregate_state(await get_all_episodes(db, request.id))
```

---

## Edge Cases

### Torrent Removed from qBit

```python
# Torrent was tracked but disappeared from qBit
# Could be: manual delete, import complete, error
# Don't change state - wait for Import webhook from Radarr/Sonarr
logger.warning(f"Tracked torrent missing from qBit: {hash[:8]}...")
```

### Progress Jumps (Fast Downloads)

Fast downloads might jump from 0% to 100% between polls:

```python
# Handle direct 0→100 transition
if is_download_complete(torrent) and episode.state in [EpisodeState.GRABBING, EpisodeState.DOWNLOADING]:
    episode.state = EpisodeState.DOWNLOADED
```

### Stalled Downloads

```python
if torrent.state == "stalledDL" and torrent.eta == -1:
    # Download stalled with no ETA - might need user attention
    logger.warning(f"Download stalled: {torrent.name}")
    # Could trigger notification to admin
```

---

## Data Stored During Phase 3

### Movies
```python
request.download_progress = 75  # 0-100
request.state = RequestState.DOWNLOADING  # or DOWNLOADED
```

### TV Episodes
```python
# Progress derived from qBit at runtime, not stored per-episode
episode.state = EpisodeState.DOWNLOADING  # or DOWNLOADED
```

---

## Investigation Items

- [ ] Confirm `downloadId` from Radarr/Sonarr matches qBit `hash` format
- [ ] Test multi-file torrent progress reporting

---

## Previous Phase

← [Phase 2: Indexer Grab](phase-2-indexer-grab.md)

## Next Phase

→ [Phase 4: Import](phase-4-import.md)
