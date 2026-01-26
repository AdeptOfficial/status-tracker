# Request Addition Flow

**Purpose:** Track media requests from initial request through availability in Jellyfin.

## Flow Overview

```
Phase 1        Phase 2         Phase 3          Phase 4         Phase 5
────────────────────────────────────────────────────────────────────────────

Jellyseerr  →  Radarr/Sonarr  →  qBittorrent  →  Radarr/Sonarr  →  Verification
   │              │                 │                │                │
   ▼              ▼                 ▼                ▼                ▼
APPROVED      GRABBING         DOWNLOADING       IMPORTING        AVAILABLE
              INDEXED
```

## 4 Media Paths

All paths are **identical** through Phase 4. They diverge at Phase 5 (Verification):

| Path | Type | Phase 5 Verification |
|------|------|----------------------|
| 1 | Regular Movie | Jellyfin TMDB lookup |
| 2 | Regular TV | Jellyfin TVDB lookup |
| 3 | Anime Movie | Shoko SignalR → Jellyfin |
| 4 | Anime TV | Shoko SignalR → Jellyfin |

## State Machine

```
                                    ┌──────────────────────────┐
                                    │                          │
REQUESTED ──► APPROVED ──► GRABBING ──► INDEXED ──► DOWNLOADING ──► IMPORTING
                                                                       │
                              ┌────────────────────────────────────────┤
                              │                                        │
                              ▼                                        ▼
                       ANIME_MATCHING ────────────────────────►   AVAILABLE
                              │                                        ▲
                              └───────── (fallback checker) ───────────┘
```

## Phase Documents

| Phase | Document | Trigger | Key Data |
|-------|----------|---------|----------|
| 1 | [Request Creation](phase-1-request-creation.md) | Jellyseerr webhook | tmdb_id, tvdb_id, poster_url |
| 2 | [Indexer Grab](phase-2-indexer-grab.md) | Radarr/Sonarr Grab | download_id (qbit hash), quality |
| 3 | [Download Progress](phase-3-download-progress.md) | qBittorrent polling | progress %, ETA |
| 4 | [Import](phase-4-import.md) | Radarr/Sonarr Download | final_path |
| 5 | [Verification](phase-5-verification.md) | Varies by path | Jellyfin item ID |

## Correlation Strategy

**Priority order** (most reliable first):

1. `download_id` (qbit hash) - Unique per download
2. `jellyseerr_id` - Unique per request
3. `tmdb_id` + state filter - Good for movies
4. `tvdb_id` + state filter - Good for TV
5. `final_path` - Good for Shoko correlation

**Critical rule:** All correlation queries MUST exclude terminal states (`AVAILABLE`, `DELETED`).

## Known Bugs

| # | Bug | Fix Location | Status |
|---|-----|--------------|--------|
| 1 | Correlation matches wrong request | `correlator.py` | Documented |
| 2 | TV fallback missing | `jellyfin_verifier.py` | Documented |
| 3 | Anime ID mismatch | `jellyfin_verifier.py` | Documented |
| 4 | Poster URL field | `jellyseerr.py` | **Fixed** |
| 5 | Library sync phantom requests | `library_sync.py` | Documented |

See individual phase docs for detailed fix implementations.
