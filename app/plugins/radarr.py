"""Radarr plugin - handles movie grab, import, and deletion webhooks.

Radarr sends webhooks for:
- Grab: Movie found on indexer, sent to download client
- Download: Movie file imported to library
- MovieDelete: Movie removed from Radarr
- MovieFileDelete: Movie file removed

Webhook setup in Radarr:
  Settings -> Connect -> + -> Webhook
  URL: http://status-tracker:8000/hooks/radarr
  Method: POST
  Events: On Grab, On Import, On Movie Delete, On Movie File Delete
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


class RadarrPlugin(ServicePlugin):
    """Handles Radarr webhook events for movies."""

    @property
    def name(self) -> str:
        return "radarr"

    @property
    def display_name(self) -> str:
        return "Radarr"

    @property
    def states_provided(self) -> list[RequestState]:
        return [RequestState.INDEXED, RequestState.IMPORTING]

    @property
    def correlation_fields(self) -> list[str]:
        return ["tmdb_id", "qbit_hash"]

    async def handle_webhook(
        self, payload: dict, db: "AsyncSession"
    ) -> Optional[MediaRequest]:
        """
        Process Radarr webhook.

        Grab payload structure:
        {
            "eventType": "Grab",
            "movie": {
                "id": 1,
                "title": "Movie Name",
                "year": 2022,
                "tmdbId": 414906,
                "imdbId": "tt1234567"
            },
            "remoteMovie": {
                "tmdbId": 414906,
                "imdbId": "tt1234567",
                "title": "Movie Name",
                "year": 2022
            },
            "release": {
                "quality": "Bluray-1080p",
                "releaseTitle": "Movie.Name.2022.1080p.BluRay",
                "indexer": "1337x",
                "size": 1234567890
            },
            "downloadClient": "qBittorrent",
            "downloadId": "ABC123DEF456..."  # qBittorrent hash
        }

        Download (Import) payload structure:
        {
            "eventType": "Download",
            "movie": {...},
            "remoteMovie": {...},
            "movieFile": {
                "id": 1,
                "relativePath": "Movie Name (2022)/Movie.Name.2022.1080p.BluRay.mkv",
                "path": "/data/movies/Movie Name (2022)/...",
                "quality": "Bluray-1080p"
            },
            "downloadClient": "qBittorrent",
            "downloadId": "ABC123DEF456..."
        }
        """
        event_type = payload.get("eventType", "")
        movie = payload.get("movie", {})
        release = payload.get("release", {})

        logger.info(f"Radarr webhook: {event_type}")

        # Extract IDs for correlation
        tmdb_id = movie.get("tmdbId")
        download_id = payload.get("downloadId")  # qBittorrent hash

        if not tmdb_id:
            logger.warning("Radarr webhook missing tmdbId")
            return None

        # Find existing request by tmdb_id or download hash
        request = await correlator.find_by_any(
            db,
            tmdb_id=tmdb_id,
            qbit_hash=download_id,
        )

        if not request:
            logger.debug(f"No matching request found for tmdbId={tmdb_id}")
            return None

        if event_type == "Grab":
            return await self._handle_grab(request, payload, db)

        if event_type == "Download":
            return await self._handle_download(request, payload, db)

        if event_type == "MovieDelete":
            # Movie deleted in Radarr - sync deletion to other services
            await self._handle_movie_delete(request, payload, db)
            return None  # Request is deleted, can't return it

        if event_type == "MovieFileDelete":
            # Movie file deleted - could be manual or cleanup
            logger.info(f"Radarr movie file delete for {request.title}")
            # Don't delete the request, just log it (file cleanup is normal)
            return None

        if event_type == "Test":
            logger.info("Radarr test webhook received")
            return None

        logger.debug(f"Unhandled Radarr event: {event_type}")
        return None

    async def _handle_grab(
        self, request: MediaRequest, payload: dict, db: "AsyncSession"
    ) -> MediaRequest:
        """Handle Grab event - movie found on indexer."""
        movie = payload.get("movie", {})
        release = payload.get("release", {})

        # Store the Radarr movie ID for deletion sync
        radarr_id = movie.get("id")
        if radarr_id:
            request.radarr_id = radarr_id

        # Store the qBittorrent hash for later correlation
        download_id = payload.get("downloadId")
        if download_id:
            request.qbit_hash = download_id

        # Store quality and indexer info
        quality = release.get("quality") or release.get("qualityName", "Unknown")
        indexer = release.get("indexer", "")
        request.quality = quality
        request.indexer = indexer

        # Store year if available
        year = movie.get("year")
        if year:
            request.year = year

        # Build human-readable details
        details = f"{quality}"
        if indexer:
            details += f" from {indexer}"
        if year:
            details += f" ({year})"

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
            f"Radarr grab: {request.title} - {quality} "
            f"(hash: {download_id[:8] if download_id else 'N/A'}...)"
        )
        return request

    async def _handle_download(
        self, request: MediaRequest, payload: dict, db: "AsyncSession"
    ) -> MediaRequest:
        """Handle Download (Import) event - file imported to library."""
        movie = payload.get("movie", {})
        movie_file = payload.get("movieFile", {})

        # Store the Radarr movie ID if not already set (redundancy)
        radarr_id = movie.get("id")
        if radarr_id and not request.radarr_id:
            request.radarr_id = radarr_id

        # Store file path for Shoko/Jellyfin correlation
        file_path = movie_file.get("path", "")
        if file_path:
            request.final_path = file_path

        # Update quality if not already set
        if not request.quality:
            request.quality = movie_file.get("quality", "")

        details = "Imported to library"
        if file_path:
            # Show just the filename for readability
            filename = file_path.split("/")[-1] if "/" in file_path else file_path
            details = f"Importing: {filename}"

        await state_machine.transition(
            request,
            RequestState.IMPORTING,
            db,
            service=self.name,
            event_type="Import",
            details=details,
            raw_data=payload,
        )

        logger.info(f"Radarr import: {request.title}")
        return request

    async def _handle_movie_delete(
        self, request: MediaRequest, payload: dict, db: "AsyncSession"
    ) -> None:
        """Handle MovieDelete event - movie removed from Radarr externally."""
        if not settings.ENABLE_DELETION_SYNC:
            logger.info(
                f"Radarr MovieDelete for {request.title}, but deletion sync disabled"
            )
            return

        from app.services.deletion_orchestrator import delete_request

        movie = payload.get("movie", {})
        delete_files = payload.get("deletedFiles", False)

        logger.info(
            f"Radarr MovieDelete: {request.title} "
            f"(deleteFiles={delete_files})"
        )

        # Delete from status-tracker and sync to OTHER services (skip radarr since it triggered this)
        await delete_request(
            db=db,
            request_id=request.id,
            user_id=None,
            username="Radarr",
            delete_files=delete_files,
            source=DeletionSource.RADARR,
            skip_services=["radarr"],  # Already deleted from Radarr
        )

    def get_timeline_details(self, event_data: dict) -> str:
        """Format event for timeline display."""
        event_type = event_data.get("eventType", "")
        release = event_data.get("release", {})
        movie_file = event_data.get("movieFile", {})

        if event_type == "Grab":
            quality = release.get("quality", "Unknown")
            indexer = release.get("indexer", "")
            return f"{quality}" + (f" from {indexer}" if indexer else "")

        if event_type == "Download":
            path = movie_file.get("relativePath", "")
            return f"Imported: {path}" if path else "Import complete"

        return ""
