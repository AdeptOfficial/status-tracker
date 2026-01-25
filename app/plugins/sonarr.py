"""Sonarr plugin - handles TV series grab, import, and deletion webhooks.

Sonarr sends webhooks for:
- Grab: Series found on indexer, sent to download client
- Download: Episode file imported to library
- SeriesDelete: Series removed from Sonarr
- EpisodeFileDelete: Episode file removed

Webhook setup in Sonarr:
  Settings -> Connect -> + -> Webhook
  URL: http://status-tracker:8000/hooks/sonarr
  Method: POST
  Events: On Grab, On Import, On Series Delete, On Episode File Delete

Episode Tracking:
- On Grab: Creates Episode rows for each episode in the download
- On Import: Updates Episode rows with final_path and transitions state
- Season packs: All episodes share the same qbit_hash, one import webhook
"""

import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select

from app.core.plugin_base import ServicePlugin
from app.core.correlator import correlator
from app.core.state_machine import state_machine
from app.models import MediaRequest, RequestState, DeletionSource, Episode, EpisodeState
from app.config import settings
from app.services.state_calculator import calculate_aggregate_state

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class SonarrPlugin(ServicePlugin):
    """Handles Sonarr webhook events for TV series."""

    @property
    def name(self) -> str:
        return "sonarr"

    @property
    def display_name(self) -> str:
        return "Sonarr"

    @property
    def states_provided(self) -> list[RequestState]:
        return [RequestState.GRABBING, RequestState.IMPORTING]

    @property
    def correlation_fields(self) -> list[str]:
        return ["tvdb_id", "qbit_hash"]

    async def handle_webhook(
        self, payload: dict, db: "AsyncSession"
    ) -> Optional[MediaRequest]:
        """
        Process Sonarr webhook.

        Grab payload structure:
        {
            "eventType": "Grab",
            "series": {
                "id": 1,
                "title": "Show Name",
                "tvdbId": 12345,
                "imdbId": "tt1234567",
                "type": "standard"
            },
            "episodes": [{
                "episodeNumber": 1,
                "seasonNumber": 1,
                "title": "Episode Title"
            }],
            "release": {
                "quality": "WEBDL-1080p",
                "releaseTitle": "Show.Name.S01E01.1080p.WEB-DL",
                "indexer": "1337x",
                "size": 1234567890
            },
            "downloadClient": "qBittorrent",
            "downloadId": "ABC123DEF456..."  # qBittorrent hash
        }

        Download (Import) payload structure:
        {
            "eventType": "Download",
            "series": {...},
            "episodes": [{...}],
            "episodeFile": {
                "id": 1,
                "relativePath": "Season 01/Show.Name.S01E01.1080p.WEB-DL.mkv",
                "path": "/data/tv/shows/Show Name/Season 01/...",
                "quality": "WEBDL-1080p"
            },
            "downloadClient": "qBittorrent",
            "downloadId": "ABC123DEF456..."
        }
        """
        event_type = payload.get("eventType", "")
        series = payload.get("series", {})
        release = payload.get("release", {})

        logger.info(f"Sonarr webhook: {event_type}")

        # Extract IDs for correlation
        tvdb_id = series.get("tvdbId")
        download_id = payload.get("downloadId")  # qBittorrent hash

        if not tvdb_id:
            logger.warning("Sonarr webhook missing tvdbId")
            return None

        # Find existing request by tvdb_id or download hash
        request = await correlator.find_by_any(
            db,
            tvdb_id=tvdb_id,
            qbit_hash=download_id,
        )

        if not request:
            logger.debug(f"No matching request found for tvdbId={tvdb_id}")
            return None

        if event_type == "Grab":
            return await self._handle_grab(request, payload, db)

        if event_type == "Download":
            return await self._handle_download(request, payload, db)

        if event_type == "SeriesDelete":
            # Series deleted in Sonarr - sync deletion to other services
            await self._handle_series_delete(request, payload, db)
            return None  # Request is deleted, can't return it

        if event_type == "EpisodeFileDelete":
            # Episode file deleted - could be manual or cleanup
            logger.info(f"Sonarr episode file delete for {request.title}")
            # Don't delete the request, just log it (file cleanup is normal)
            return None

        if event_type == "Test":
            logger.info("Sonarr test webhook received")
            return None

        logger.debug(f"Unhandled Sonarr event: {event_type}")
        return None

    async def _handle_grab(
        self, request: MediaRequest, payload: dict, db: "AsyncSession"
    ) -> MediaRequest:
        """Handle Grab event - series found on indexer.

        Creates Episode rows for each episode in the download.
        All episodes in a season pack share the same qbit_hash.

        For per-episode grabs, this is called multiple times (once per episode).
        We query Sonarr API for the actual episode count on first grab.
        """
        series = payload.get("series", {})
        release = payload.get("release", {})
        episodes_data = payload.get("episodes", [])
        download_id = payload.get("downloadId")

        # Debug log the webhook payload structure
        logger.debug(
            f"Sonarr Grab webhook: series={series.get('title')}, "
            f"seriesId={series.get('id')}, tvdbId={series.get('tvdbId')}, "
            f"episodes_count={len(episodes_data)}, downloadId={download_id[:16] if download_id else 'N/A'}..."
        )
        if episodes_data:
            ep_summary = [f"S{e.get('seasonNumber', 0):02d}E{e.get('episodeNumber', 0):02d}" for e in episodes_data[:5]]
            if len(episodes_data) > 5:
                ep_summary.append(f"...+{len(episodes_data) - 5} more")
            logger.debug(f"Sonarr Grab episodes: {', '.join(ep_summary)}")

        # Store the Sonarr series ID for deletion sync
        sonarr_id = series.get("id")
        if sonarr_id:
            request.sonarr_id = sonarr_id

        # Store the qBittorrent hash for later correlation
        # NOTE: Only set on first grab to avoid overwriting when multiple torrents
        # are grabbed (e.g., season pack + missing episodes). Episode-level hashes
        # are the source of truth for multi-torrent tracking.
        if download_id and not request.qbit_hash:
            request.qbit_hash = download_id

        # Store IMDB ID from series
        imdb_id = series.get("imdbId")
        if imdb_id:
            request.imdb_id = imdb_id

        # Detect is_anime from series type
        # Sonarr uses "seriesType" in webhooks, but may also use "type" in some contexts
        series_type = series.get("seriesType") or series.get("type", "")
        request.is_anime = series_type.lower() == "anime"

        # Store quality and indexer info
        quality = release.get("quality") or release.get("qualityName", "Unknown")
        indexer = release.get("indexer", "")
        request.quality = quality
        request.indexer = indexer

        # Store release info
        request.file_size = release.get("size")
        request.release_group = release.get("releaseGroup")

        # CREATE EPISODE ROWS from webhook data (no API call needed!)
        # For per-episode grabs, check if episode already exists to avoid duplicates
        for ep_data in episodes_data:
            season_num = ep_data.get("seasonNumber")
            episode_num = ep_data.get("episodeNumber")

            # Check if episode already exists
            stmt = select(Episode).where(
                Episode.request_id == request.id,
                Episode.season_number == season_num,
                Episode.episode_number == episode_num,
            )
            result = await db.execute(stmt)
            existing = result.scalar_one_or_none()

            if existing:
                # Update hash if different (new grab for same episode)
                if download_id and existing.qbit_hash != download_id:
                    existing.qbit_hash = download_id
                    existing.state = EpisodeState.GRABBING
                    logger.debug(f"Updated existing episode S{season_num:02d}E{episode_num:02d} with new hash")
            else:
                episode = Episode(
                    request_id=request.id,
                    season_number=season_num,
                    episode_number=episode_num,
                    episode_title=ep_data.get("title"),
                    sonarr_episode_id=ep_data.get("id"),
                    episode_tvdb_id=ep_data.get("tvdbId"),
                    qbit_hash=download_id,  # All share same hash for season pack
                    state=EpisodeState.GRABBING,
                )
                db.add(episode)
                logger.debug(f"Created new episode S{season_num:02d}E{episode_num:02d}")

        # Don't overwrite total_episodes if already set by Jellyseerr at request creation
        # This preserves the accurate count for per-episode grab progress display
        if not request.total_episodes:
            # Fallback only if Jellyseerr didn't set it (shouldn't happen for TV)
            request.total_episodes = len(episodes_data)
            logger.debug(f"Set total_episodes={len(episodes_data)} from webhook (fallback)")

        # Store season info from first episode (for display)
        if episodes_data:
            first_ep = episodes_data[0]
            request.season = first_ep.get("seasonNumber")

        # Build human-readable details
        details = f"{quality}"
        if indexer:
            details += f" from {indexer}"
        if len(episodes_data) == 1:
            ep = episodes_data[0]
            details += f" (S{ep.get('seasonNumber', 0):02d}E{ep.get('episodeNumber', 0):02d})"
        elif len(episodes_data) > 1:
            details += f" ({len(episodes_data)} episodes)"

        await state_machine.transition(
            request,
            RequestState.GRABBING,
            db,
            service=self.name,
            event_type="Grab",
            details=details,
            raw_data=payload,
        )

        logger.info(
            f"Sonarr grab: {request.title} - {quality} "
            f"({len(episodes_data)} episodes, hash: {download_id[:8] if download_id else 'N/A'}..., "
            f"is_anime={request.is_anime})"
        )
        return request

    async def _handle_download(
        self, request: MediaRequest, payload: dict, db: "AsyncSession"
    ) -> MediaRequest:
        """Handle Download (Import) event - file imported to library.

        Handles both:
        - Season pack: episodeFiles[] (plural) - ONE webhook for all
        - Single episode: episodeFile (singular) - one webhook per episode
        """
        series = payload.get("series", {})
        episodes_data = payload.get("episodes", [])

        # Season pack: episodeFiles[] (plural)
        # Single episode: episodeFile (singular)
        episode_files = payload.get("episodeFiles", [])
        if not episode_files:
            single = payload.get("episodeFile")
            if single:
                episode_files = [single]

        # Store the Sonarr series ID if not already set (redundancy)
        sonarr_id = series.get("id")
        if sonarr_id and not request.sonarr_id:
            request.sonarr_id = sonarr_id

        # Update request final_path to series/season folder
        destination_path = payload.get("destinationPath") or series.get("path")
        if destination_path:
            request.final_path = destination_path

        # Detect is_anime from path if not already set (fallback detection)
        if request.is_anime is None:
            request.is_anime = "/anime/" in (destination_path or "").lower()

        # Determine target state based on anime flag
        target_episode_state = EpisodeState.ANIME_MATCHING if request.is_anime else EpisodeState.IMPORTING

        # Match episodes to files and update their state
        updated_count = 0
        for i, ep_data in enumerate(episodes_data):
            season_num = ep_data.get("seasonNumber")
            episode_num = ep_data.get("episodeNumber")

            # Find the Episode row
            stmt = select(Episode).where(
                Episode.request_id == request.id,
                Episode.season_number == season_num,
                Episode.episode_number == episode_num,
            )
            result = await db.execute(stmt)
            episode = result.scalar_one_or_none()

            if episode and i < len(episode_files):
                episode.final_path = episode_files[i].get("path")
                episode.state = target_episode_state
                updated_count += 1
            elif episode:
                # No file for this episode yet (partial import)
                episode.state = target_episode_state

        # Recalculate aggregate state from episodes
        # Need to reload episodes for aggregation
        from sqlalchemy.orm import selectinload
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db.execute(stmt)
        request = result.scalar_one()

        # Calculate aggregate state
        new_state = calculate_aggregate_state(request)

        # Build details
        if len(episode_files) == 1:
            filename = episode_files[0].get("relativePath", "").split("/")[-1]
            details = f"Imported: {filename}"
        else:
            details = f"Imported {len(episode_files)} episodes"

        await state_machine.transition(
            request,
            new_state,
            db,
            service=self.name,
            event_type="Import",
            details=details,
            raw_data=payload,
        )

        logger.info(
            f"Sonarr import: {request.title} - {updated_count} episodes updated "
            f"({new_state.value})"
        )
        return request

    async def _handle_series_delete(
        self, request: MediaRequest, payload: dict, db: "AsyncSession"
    ) -> None:
        """Handle SeriesDelete event - series removed from Sonarr externally."""
        if not settings.ENABLE_DELETION_SYNC:
            logger.info(
                f"Sonarr SeriesDelete for {request.title}, but deletion sync disabled"
            )
            return

        from app.services.deletion_orchestrator import delete_request

        series = payload.get("series", {})
        delete_files = payload.get("deletedFiles", False)

        logger.info(
            f"Sonarr SeriesDelete: {request.title} "
            f"(deleteFiles={delete_files})"
        )

        # Delete from status-tracker and sync to OTHER services (skip sonarr since it triggered this)
        await delete_request(
            db=db,
            request_id=request.id,
            user_id=None,
            username="Sonarr",
            delete_files=delete_files,
            source=DeletionSource.SONARR,
            skip_services=["sonarr"],  # Already deleted from Sonarr
        )

    def get_timeline_details(self, event_data: dict) -> str:
        """Format event for timeline display."""
        event_type = event_data.get("eventType", "")
        release = event_data.get("release", {})
        episode_file = event_data.get("episodeFile", {})

        if event_type == "Grab":
            quality = release.get("quality", "Unknown")
            indexer = release.get("indexer", "")
            return f"{quality}" + (f" from {indexer}" if indexer else "")

        if event_type == "Download":
            path = episode_file.get("relativePath", "")
            return f"Imported: {path}" if path else "Import complete"

        return ""
