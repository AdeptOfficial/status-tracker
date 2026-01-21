# Testing Session: Jellyfin Verification Flow for Anime Movies

**Date:** 2026-01-21
**Status:** READY FOR RETEST - Bugs fixed, using different test movie

## Summary of Fixes Applied This Session

### Fix 1: Fallback Checks IMPORTING State (deployed)
**File:** `app/services/jellyfin_verifier.py`

The fallback checker now queries both `IMPORTING` and `ANIME_MATCHING` states for movies. This catches cases where Shoko events weren't received (already-known files, SignalR drops).

### Fix 2: FileDetected Handler (deployed)
**File:** `app/clients/shoko.py`

Added handler for `ShokoEvent:FileDetected` to log when Shoko detects files. Helps debug when FileMatched events aren't sent.

### Fix 3: Verify Playable Items (deployed)
**File:** `app/clients/jellyfin.py`

`find_item_by_tmdb()` now requests `MediaSources` and `Path` fields and verifies items are playable before returning them. Prevents false-positive AVAILABLE status from metadata-only stubs (e.g., Jellyseerr sync items).

### Fix 4: Scan Trigger + State Transition (deployed)
**File:** `app/services/jellyfin_verifier.py`

Fallback checker now:
1. Triggers Jellyfin library scan when it finds IMPORTING movies
2. Transitions IMPORTING → ANIME_MATCHING to show progress while waiting for Shokofin

## Bugs Documented (Not Yet Fixed)

### Bug: Deletion Should Remove qBittorrent Torrent
**File:** `issues/deletion-remove-qbittorrent-torrent.md`

When deleting media, the torrent and files should be removed from qBittorrent with `deleteFiles=true`. Otherwise, re-requesting the same content causes instant-completion that Radarr can't track.

### Bug: Metadata-Only Items Returned as Available
**File:** `issues/jellyfin-verify-playable-item.md`

Documented the root cause of false-positive AVAILABLE status. Fixed by verify playable items change above.

## Test Case: Rascal Does Not Dream of a Dreaming Girl (2019)

**Why this movie:** Shorter runtime = shorter download wait time

**TMDB ID:** To be determined when requested

### Expected Flow After Fixes

1. Jellyseerr request → APPROVED
2. Radarr grab → INDEXED
3. qBittorrent download → DOWNLOADING → DOWNLOAD_DONE
4. Radarr import → IMPORTING
5. Fallback checker finds IMPORTING movie → triggers Jellyfin scan
6. Fallback transitions → ANIME_MATCHING (shows "Detected in library scan...")
7. Shokofin syncs the movie to Jellyfin
8. Next fallback cycle finds playable item → AVAILABLE (with jellyfin_id)

### Key Logs to Watch

```bash
# Watch for fallback activity
ssh root@10.0.2.10 'pct exec 220 -- docker logs -f status-tracker 2>&1' | grep -E "(FALLBACK|JELLYFIN|metadata-only|playable)"

# Watch for Shoko events
ssh root@10.0.2.10 'pct exec 220 -- docker logs -f status-tracker 2>&1' | grep -E "(SHOKO|FileDetected|FileMatched|MovieUpdated)"

# Check request state
curl -s http://10.0.2.20:8100/api/requests | jq '.requests | map(select(.title | test("Rascal.*Dream.*Girl"; "i"))) | .[0] | {id, title, state, jellyfin_id}'
```

## Environment Status (Verified)

| Service | Status |
|---------|--------|
| Status-tracker | ✅ healthy |
| Shoko SignalR | ✅ connected |
| VPN (Gluetun) | ✅ IP: 146.70.112.174 |
| Radarr ↔ qBittorrent | ✅ no errors |
| qBittorrent auth | ✅ 172.18.0.0/16 whitelisted |

## Files Modified This Session

| File | Changes |
|------|---------|
| `app/clients/jellyfin.py` | `find_item_by_tmdb()` verifies playable items |
| `app/clients/shoko.py` | Added `_handle_file_detected()` handler |
| `app/services/jellyfin_verifier.py` | Fallback checks IMPORTING, triggers scan, transitions |

## Resume Prompt

After compacting, use this prompt:

---

**Resume testing Jellyfin verification flow for anime movies.**

Context file: `apps/status-tracker/issues/testing-jellyfin-verification-flow.md`

Current state:
- Fixes deployed: playable item verification, fallback scan trigger, IMPORTING state handling
- Ready to test with: Rascal Does Not Dream of a Dreaming Girl (2019)
- All services verified healthy, VPN connected

The fix ensures:
1. `find_item_by_tmdb()` only returns items with MediaSources/Path (not metadata stubs)
2. Fallback triggers Jellyfin scan for IMPORTING movies
3. Fallback transitions IMPORTING → ANIME_MATCHING while waiting for Shokofin

Please monitor the flow when I request the movie. Only monitor, no manual triggers, follow security protocol (no reading .env, config files, no env/printenv commands).

---
