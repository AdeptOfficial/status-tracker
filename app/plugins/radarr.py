"""Radarr plugin - handles movie grab, import, and deletion webhooks.

Radarr sends webhooks for:
- Grab: Movie found on indexer, sent to download client
- Download: Movie file imported to library
- MovieAdded: Movie added to Radarr (used to sync alternate titles for anime)
- MovieDelete: Movie removed from Radarr
- MovieFileDelete: Movie file removed

Webhook setup in Radarr:
  Settings -> Connect -> + -> Webhook
  URL: http://status-tracker:8000/hooks/radarr
  Method: POST
  Events: On Grab, On Import, On Movie Added, On Movie Delete, On Movie File Delete
"""

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Optional

from app.core.plugin_base import ServicePlugin
from app.core.correlator import correlator
from app.core.state_machine import state_machine
from app.models import MediaRequest, RequestState, DeletionSource
from app.config import settings
from app.clients.radarr import radarr_client
from app.database import async_session_maker
from app.services.anime_title_sync import sync_anime_titles_background

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
        return [RequestState.GRABBING, RequestState.IMPORTING]

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

        if event_type == "MovieAdded":
            # Movie added to Radarr - sync alternate titles for anime
            await self._handle_movie_added(payload, db)
            return None  # Don't return request, just process titles

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

        # Store IMDB ID from movie
        imdb_id = movie.get("imdbId")
        if imdb_id:
            request.imdb_id = imdb_id

        # Detect is_anime from tags array
        tags = movie.get("tags", [])
        request.is_anime = "anime" in [str(t).lower() for t in tags]

        # Store quality and indexer info
        quality = release.get("quality") or release.get("qualityName", "Unknown")
        indexer = release.get("indexer", "")
        request.quality = quality
        request.indexer = indexer

        # Store release info
        request.file_size = release.get("size")
        request.release_group = release.get("releaseGroup")

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
            RequestState.GRABBING,
            db,
            service=self.name,
            event_type="Grab",
            details=details,
            raw_data=payload,
        )

        logger.info(
            f"Radarr grab: {request.title} - {quality} "
            f"(hash: {download_id[:8] if download_id else 'N/A'}..., is_anime={request.is_anime})"
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

        # Store file path for Shoko/Jellyfin correlation - CRITICAL for anime matching
        file_path = movie_file.get("path", "")
        if file_path:
            request.final_path = file_path

        # Update quality if not already set
        if not request.quality:
            request.quality = movie_file.get("quality", "")

        # Detect is_anime from path if not already set (fallback detection)
        if request.is_anime is None:
            # Check if path contains /anime/ directory
            request.is_anime = "/anime/" in file_path.lower() if file_path else False

        # Get filename for details
        filename = ""
        if file_path:
            filename = file_path.split("/")[-1] if "/" in file_path else file_path

        # Route to appropriate state based on is_anime flag
        if request.is_anime:
            # Anime needs Shoko matching before Jellyfin verification
            target_state = RequestState.ANIME_MATCHING
            details = f"Waiting for Shoko: {filename}" if filename else "Waiting for Shoko match"
        else:
            # Regular movie goes directly to IMPORTING for Jellyfin verification
            target_state = RequestState.IMPORTING
            details = f"Imported: {filename}" if filename else "Imported to library"

        await state_machine.transition(
            request,
            target_state,
            db,
            service=self.name,
            event_type="Import",
            details=details,
            raw_data=payload,
        )

        logger.info(f"Radarr import: {request.title} -> {target_state.value}")
        return request

    async def _handle_movie_added(
        self, payload: dict, db: "AsyncSession"
    ) -> None:
        """Handle MovieAdded event - sync alternate titles for anime releases.

        When a movie is added to Radarr, check if we have a matching request
        and trigger the anime title sync service in background.
        """
        movie = payload.get("movie", {})
        tmdb_id = movie.get("tmdbId")
        title = movie.get("title", "Unknown")

        if not tmdb_id:
            logger.debug(f"MovieAdded missing tmdbId for '{title}'")
            return

        # Find our request for this movie
        request = await correlator.find_by_any(db, tmdb_id=tmdb_id)
        if not request:
            logger.debug(f"No matching request for MovieAdded: '{title}'")
            return

        logger.info(f"MovieAdded: '{title}' - triggering anime title sync")

        # Run title sync in background (service handles anime detection)
        asyncio.create_task(
            sync_anime_titles_background(
                async_session_maker,
                request.id,
                tmdb_id,
            )
        )

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
