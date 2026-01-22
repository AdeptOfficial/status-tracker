# Phase 3 Questions (Download Progress)

## Answered

### Q1: Download progress for shared hash

When multiple episodes share a hash (multi-ep grab), they all show the same progress.

```
Episode 3  "Killing Magic"     ⬇ 68%
Episode 4  "The Mage's Secret" ⬇ 68%  (same hash ABC)
```

**Decision:** Confirmed - derive progress from hash, all episodes with that hash show same %.

### Q2: DOWNLOADING → DOWNLOADED transition trigger

When does an Episode transition from DOWNLOADING to DOWNLOADED?

**Decision:** C - Either condition triggers transition:
- qBit hash progress reaches 100%
- qBit reports seeding state ("uploading", "stalledUP", "forcedUP", "pausedUP")

```python
is_complete = (
    torrent.progress >= 1.0 or
    torrent.state in ("uploading", "stalledUP", "forcedUP", "pausedUP")
)
```

### Q3: Display counts during download

What to show for TV during download phase?

**Decision:** B - Show all three counts:
```
"3 downloaded, 5 downloading, 4 queued"
```

Where:
- downloaded = Episode.state == DOWNLOADED
- downloading = Episode.state == DOWNLOADING
- queued = Episode.state == GRABBING (waiting in qBit queue)

### Q4: Adaptive polling frequency

**Decision:** D - Adaptive polling:
- 5 seconds when downloads active
- 30 seconds when idle (no active downloads)

```python
async def get_poll_interval(db) -> int:
    active_count = await count_active_downloads(db)
    return 5 if active_count > 0 else 30
```

### Q5: Hash lookup filtering

When qBit reports progress for a hash, how do we find the right episodes?

**Decision:** Filter by request state to avoid updating old completed requests:

```python
episodes = db.query(Episode).join(MediaRequest).filter(
    Episode.qbit_hash == torrent_hash,
    MediaRequest.state.not_in([RequestState.AVAILABLE, RequestState.DELETED])
).all()
```

---

## Open

### Q6: qBit hash format

Is `downloadId` from Radarr/Sonarr the same format as qBit's `hash` field?

**Status:** ANSWERED ✓

**Finding:** Yes, `downloadId` IS the qBit hash.
- 40 character uppercase hex string (SHA1)
- Example: `C2C60F66C126652A86F7F2EE73DC83D4E255929E`
- Captured from Radarr Grab webhook on 2026-01-21

### Q7: Multi-file torrent progress

For season packs (one hash, many files), does qBit report:
- A) Overall torrent progress
- B) Per-file progress

**Status:** INVESTIGATE - Test with real season pack
