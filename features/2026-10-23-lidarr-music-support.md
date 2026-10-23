# Lidarr (music) support

**Created:** 2026-10-23
**Status:** Planned (future; requested by the owner 2026-10-23, after Lidarr was set up on DEV)
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

## Acceptance

On DEV, adding and searching one album in Lidarr creates a music request in Status Tracker that shows
grab, per-track download progress, import and *Available* once the player lists all tracks; the
existing movie and TV flows are unchanged.
