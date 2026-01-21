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
"""

import logging
from typing import TYPE_CHECKING, Optional

from app.core.plugin_base import ServicePlugin
from app.core.correlator import correlator
from app.core.state_machine import state_machine
from app.models import MediaRequest, RequestState, DeletionSource
from app.config import settings

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
        return [RequestState.INDEXED, RequestState.IMPORTING]

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
        """Handle Grab event - series found on indexer."""
        series = payload.get("series", {})
        release = payload.get("release", {})
        episodes = payload.get("episodes", [{}])
        episode_info = episodes[0] if episodes else {}

        # Store the Sonarr series ID for deletion sync
        sonarr_id = series.get("id")
        if sonarr_id:
            request.sonarr_id = sonarr_id

        # Store the qBittorrent hash for later correlation
        download_id = payload.get("downloadId")
        if download_id:
            request.qbit_hash = download_id

        # Store quality and indexer info
        quality = release.get("quality") or release.get("qualityName", "Unknown")
        indexer = release.get("indexer", "")
        request.quality = quality
        request.indexer = indexer

        # Store season/episode info
        if episode_info:
            request.season = episode_info.get("seasonNumber")
            request.episode = episode_info.get("episodeNumber")

        # Build human-readable details
        details = f"{quality}"
        if indexer:
            details += f" from {indexer}"
        if episode_info.get("seasonNumber") is not None:
            details += f" (S{episode_info.get('seasonNumber', 0):02d}E{episode_info.get('episodeNumber', 0):02d})"

        await state_machine.transition(
            request,
            RequestState.INDEXED,
            db,
            service=self.name,
            event_type="Grab",
            details=details,
            raw_data=payload,
        )

        logger.info(
            f"Sonarr grab: {request.title} - {quality} "
            f"(hash: {download_id[:8] if download_id else 'N/A'}...)"
        )
        return request

    async def _handle_download(
        self, request: MediaRequest, payload: dict, db: "AsyncSession"
    ) -> MediaRequest:
        """Handle Download (Import) event - file imported to library."""
        series = payload.get("series", {})
        episode_file = payload.get("episodeFile", {})

        # Store the Sonarr series ID if not already set (redundancy)
        sonarr_id = series.get("id")
        if sonarr_id and not request.sonarr_id:
            request.sonarr_id = sonarr_id

        # Store file path for Shoko/Jellyfin correlation
        file_path = episode_file.get("path", "")
        if file_path:
            request.final_path = file_path

        # Update quality if not already set
        if not request.quality:
            request.quality = episode_file.get("quality", "")

        details = "Imported to library"
        if file_path:
            # Show just the filename for readability
            filename = file_path.split("/")[-1] if "/" in file_path else file_path
            details = f"Imported: {filename}"

        await state_machine.transition(
            request,
            RequestState.IMPORTING,
            db,
            service=self.name,
            event_type="Import",
            details=details,
            raw_data=payload,
        )

        logger.info(f"Sonarr import: {request.title}")
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
