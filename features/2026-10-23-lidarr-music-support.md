# Lidarr (music) support

**Created:** 2026-10-23
**Status:** Planned (future; requested by the owner 2026-10-23, after Lidarr was set up on DEV; design notes added the same day, not implemented)
**Priority:** Low
**From:** Lidarr DEV setup; the earlier note "Future: Lidarr Support" in the homelab's media monitoring
service doc (new client and plugin, webhook from Lidarr)
**Related:** [per-episode progress and request state](2026-01-18-per-episode-progress-and-request-state.md)

## Goal

Track music the way Status Tracker tracks movies and TV: an album appears when it is wanted or
grabbed, shows download and import progress, and reaches *Available* when it is playable in the music
player. Same dashboard, same states, same deletion and verification ideas.

## Differences from movies and TV

- **No request app in front.** Jellyseerr does not handle music. Music is added in Lidarr itself (or,
  later, in a music request front-end such as DroppedNeedle or Aurral). Status Tracker therefore has
  to create a request from Lidarr's own events (artist/album added or grabbed), not from a Jellyseerr
  request.
- **Album = request, tracks = items.** An album is one torrent with many track files. This maps
  directly onto the per-episode model: the album is the request, tracks are the rows, and file-level
  progress from qBittorrent gives per-track progress (album packs import together, like a season pack).
- **Availability** comes from the music player, not Jellyfin's video library: Navidrome (Subsonic
  API) or a Jellyfin music library, whichever the deployment uses.
- **Identity:** MusicBrainz IDs (artist, release group, release) instead of TMDB/TVDB.

## Scope (first iteration)

1. `app/clients/lidarr.py`: artist, album, queue, history and track-file reads (Lidarr API v1).
2. `app/plugins/lidarr.py`: webhook events Grab, Download/Import (AlbumDownload), Rename,
   AlbumDelete/ArtistDelete, Test; correlate by download ID and MusicBrainz release IDs.
3. Media type `MUSIC` (album) with track rows reusing the episode tracking (state, progress, file).
4. qBittorrent polling for the `lidarr` category, reusing the per-episode file progress logic.
5. Availability check against Navidrome or Jellyfin music (configurable), verifying tracks exist.
6. Dashboard: album card with artist, cover art, track progress; filter for music.

Out of the first iteration: deletion sync for music, multi-disc edge cases, artist-level tracking.

## Prerequisites

- The per-episode fixes (poll by item, progress over all items, request state rule) should land first;
  albums depend on the same machinery.
- A music player chosen for the deployment (Navidrome or Jellyfin music) for the availability check.

## Design notes from the music setup (2026-10-23, not implemented)

Findings from setting up and testing music on the owner's homelab (DEV and production). Plan only;
nothing below is built yet.

### Two download paths, not one

Lidarr gets music two ways, and only one of them goes through qBittorrent:

| Path | How it works | Where progress is visible |
|---|---|---|
| Torrents | Lidarr searches indexers (through Prowlarr) and sends a grab to qBittorrent, category `lidarr` | qBittorrent (per file), Lidarr queue and history (`grabbed`, `downloadImported`) |
| **Soulseek** | **Soularr** reads Lidarr's Wanted list, searches **slskd**, downloads, then asks Lidarr to import the folder (`DownloadedAlbumsScan`) | **slskd** API `GET /api/v0/transfers/downloads` (per user, per folder, per file: state, bytes); Lidarr only sees the import |

In the hit-rate test (30 releases from 15 artists), Soulseek found 30 in FLAC and the torrent indexer 4,
so **most music will arrive through Soulseek**, which qBittorrent polling cannot see. A music client
needs an slskd client (read-only API key is enough to read transfers) besides Lidarr and qBittorrent.

### Proposed request states for an album

| State | Meaning | Signal |
|---|---|---|
| Wanted | monitored and missing | Lidarr `wanted/missing` (album monitored **and** artist monitored) |
| Searching | a search ran, nothing grabbed yet | Lidarr search command / Soularr log "Searching for album"; no queue item, no slskd transfer |
| Downloading | files arriving | qBittorrent torrent in `lidarr`, or slskd files `InProgress` / `Completed, Succeeded` |
| **Waiting on sharer** | Soulseek user has the files queued for us | slskd files `Queued, Remotely` (seen 35+ min on a single file) |
| **Stalled / retrying** | sharer refused or a file failed; Soularr gives up after `stalled_timeout` and tries another user next run | slskd `Completed, Rejected` / `Errored` / `Aborted`; Soularr "Failed grab" |
| Importing | all files present, Lidarr importing | Soularr "Downloaded Albums Scan" / Lidarr history |
| Available | all tracks in the library and in the player | Lidarr album `trackFileCount == trackCount`, then the player lists the album (Navidrome Subsonic API, e.g. `search3` / `getAlbum`) |
| Not found | no source has a matching copy | Soularr "Failed to enqueue" over several runs and no torrent result; keep retrying quietly, show the reason |

Album = request, tracks = rows (as episodes): slskd reports each file with its own state and bytes, so
per-track progress works the same way as per-episode progress.

### Gotchas to design around

- **Artist monitoring:** an artist added with "monitor none" stays unmonitored, and its albums never
  reach Wanted even if one album is monitored later. Status Tracker should show "artist not monitored"
  instead of "Wanted" for that case.
- **Soularr works in batches** (10 albums per run) and waits for the whole batch; one slow sharer
  delays imports of finished albums in the same batch. "Downloaded, waiting for import" is a real state.
- **Multi-disc albums** need all discs from one Soulseek user; a 2-disc album can stay "Not found" while
  single-disc albums arrive.
- **Track and album names** differ between MusicBrainz and sharers (e.g. "Vices" vs "Vices (MEMPHIS MAY
  FIRE cover)", Japanese titles vs romanised); matching should use MusicBrainz IDs from Lidarr, not names.
- **Lyrics** come from the player (Navidrome plugin), not from the download; not part of "Available".
- Instance values (hosts, ports, keys) stay in the deployment's settings; this repo keeps placeholders.

### Measured on the owner's homelab (for expectations, 2026-10-23)

10 hard releases (Japanese, niche, new) monitored at once: 5 imported within 5-7 minutes; the rest
were held by a refusing sharer, a remote queue, a broken file or no match. Soularr settings were then
changed (stall limit 15 min, skip failed users for a week) and re-tested.

## Acceptance

On DEV, adding and searching one album in Lidarr creates a music request in Status Tracker that shows
grab, per-track download progress, import and *Available* once the player lists all tracks; the
existing movie and TV flows are unchanged.
