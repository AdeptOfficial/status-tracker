"""
Deletion orchestrator service.

Coordinates deletion of media across all services:
1. Creates DeletionLog entry (audit trail)
2. Hard deletes request from DB
3. Syncs deletion to external services (Sonarr/Radarr, Shoko, Jellyfin, Jellyseerr)
4. Tracks progress via DeletionSyncEvents
5. Broadcasts SSE updates for real-time UI
"""

import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import (
    MediaRequest,
    MediaType,
    DeletionLog,
    DeletionSyncEvent,
    DeletionSource,
    DeletionStatus,
    ServiceSyncStatus,
)
from app.clients.sonarr import sonarr_client
from app.clients.radarr import radarr_client
from app.clients.jellyfin import jellyfin_client
from app.clients.jellyseerr import jellyseerr_client
from app.clients.shoko import shoko_http_client
from app.core.broadcaster import broadcaster
from app.config import settings

logger = logging.getLogger(__name__)


def extract_year_from_title(title: str) -> Optional[int]:
    """Extract year from title like 'Movie Name (2013)'."""
    match = re.search(r'\((\d{4})\)\s*$', title.strip())
    if match:
        year = int(match.group(1))
        # Sanity check - year should be reasonable (1900-2100)
        if 1900 <= year <= 2100:
            return year
    return None


def get_username_for_source(
    source: DeletionSource,
    username: Optional[str] = None,
) -> str:
    """Get appropriate username based on deletion source."""
    if source == DeletionSource.DASHBOARD:
        return username or "Unknown Admin"
    elif source == DeletionSource.SONARR:
        return "Sonarr (external)"
    elif source == DeletionSource.RADARR:
        return "Radarr (external)"
    elif source == DeletionSource.JELLYFIN:
        return "Jellyfin (external)"
    elif source == DeletionSource.SHOKO:
        return "Shoko (external)"
    else:
        return "System"


class DeletionOrchestrator:
    """
    Orchestrates media deletion across all services.

    Usage:
        async with async_session() as db:
            orchestrator = DeletionOrchestrator(db)
            result = await orchestrator.delete_request(
                request_id=123,
                user_id="abc123",
                username="admin",
                delete_files=True
            )
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def delete_request(
        self,
        request_id: int,
        user_id: Optional[str] = None,
        username: Optional[str] = None,
        delete_files: bool = True,
        source: DeletionSource = DeletionSource.DASHBOARD,
        skip_services: Optional[list[str]] = None,
    ) -> Optional[DeletionLog]:
        """
        Delete a media request and sync to external services.

        Args:
            request_id: ID of the request to delete
            user_id: Jellyfin user ID of who initiated deletion
            username: Username of who initiated deletion
            delete_files: If True, delete files from disk via Sonarr/Radarr
            source: What triggered the deletion
            skip_services: List of services to skip (e.g., ["sonarr"] if deletion came from Sonarr)

        Returns:
            DeletionLog entry, or None if request not found
        """
        skip_services = skip_services or []

        # Phase 1: Get request and create deletion log
        request = await self._get_request(request_id)
        if not request:
            logger.warning(f"Request {request_id} not found for deletion")
            return None

        logger.info(f"Starting deletion of request {request_id}: {request.title}")

        # Create deletion log (snapshot of what we're deleting)
        deletion_log = await self._create_deletion_log(
            request=request,
            source=source,
            user_id=user_id,
            username=username,
        )

        # Determine all services and their applicability
        services_info = self._determine_services(request, skip_services)
        services_to_sync = self._get_services_to_sync(services_info)

        # Create initial events for ALL services (not just those to sync)
        for service, info in services_info.items():
            if not info["applicable"]:
                # Service doesn't apply (e.g., Sonarr for movies)
                await self._add_sync_event(
                    deletion_log=deletion_log,
                    service=service,
                    status=ServiceSyncStatus.NOT_APPLICABLE,
                    details=f"{service.capitalize()} not applicable for this media type",
                )
            elif info["skip"]:
                # Service was explicitly skipped (e.g., deletion came from this service)
                await self._add_sync_event(
                    deletion_log=deletion_log,
                    service=service,
                    status=ServiceSyncStatus.SKIPPED,
                    details=f"Skipped (deletion originated from {service})",
                )
            elif not info["has_id"]:
                # Service applies but no ID to delete
                await self._add_sync_event(
                    deletion_log=deletion_log,
                    service=service,
                    status=ServiceSyncStatus.NOT_NEEDED,
                    details=f"No {service} ID found for this item",
                )
            else:
                # Service needs to be synced
                await self._add_sync_event(
                    deletion_log=deletion_log,
                    service=service,
                    status=ServiceSyncStatus.PENDING,
                    details=f"Waiting to sync with {service}",
                )

        await self.db.commit()

        # Broadcast deletion started (only services being synced)
        await self._broadcast_deletion_started(deletion_log, services_to_sync)

        # Phase 2: Hard delete request from DB
        await self.db.delete(request)
        await self.db.commit()
        logger.info(f"Deleted request {request_id} from database")

        # Phase 3: Sync to external services (async)
        if settings.ENABLE_DELETION_SYNC:
            await self._sync_external_services(
                deletion_log=deletion_log,
                services=services_to_sync,
                delete_files=delete_files,
            )
        else:
            logger.info("Deletion sync disabled, skipping external services")
            # Mark pending services as skipped
            for service in services_to_sync:
                await self._add_sync_event(
                    deletion_log=deletion_log,
                    service=service,
                    status=ServiceSyncStatus.SKIPPED,
                    details="Deletion sync disabled",
                )
            # Calculate final status
            await self._update_deletion_status(deletion_log)

        # Broadcast final status
        await self._broadcast_deletion_completed(deletion_log)

        return deletion_log

    async def _get_request(self, request_id: int) -> Optional[MediaRequest]:
        """Get request by ID with timeline events."""
        result = await self.db.execute(
            select(MediaRequest)
            .where(MediaRequest.id == request_id)
            .options(selectinload(MediaRequest.timeline_events))
        )
        return result.scalar_one_or_none()

    async def _create_deletion_log(
        self,
        request: MediaRequest,
        source: DeletionSource,
        user_id: Optional[str],
        username: Optional[str],
    ) -> DeletionLog:
        """Create deletion log entry (snapshot of request)."""
        # Extract year from title if not set on request
        year = request.year or extract_year_from_title(request.title)

        # Get appropriate username based on source
        resolved_username = get_username_for_source(source, username)

        deletion_log = DeletionLog(
            title=request.title,
            media_type=request.media_type,
            tmdb_id=request.tmdb_id,
            tvdb_id=request.tvdb_id,
            jellyfin_id=request.jellyfin_id,
            sonarr_id=request.sonarr_id,
            radarr_id=request.radarr_id,
            shoko_series_id=request.shoko_series_id,
            jellyseerr_id=request.jellyseerr_id,
            poster_url=request.poster_url,
            year=year,
            is_anime=request.is_anime,  # Store for Shoko sync determination
            source=source,
            deleted_by_user_id=user_id,
            deleted_by_username=resolved_username,
            status=DeletionStatus.IN_PROGRESS,
            initiated_at=datetime.utcnow(),
        )
        self.db.add(deletion_log)
        await self.db.flush()  # Get the ID
        return deletion_log

    async def _add_sync_event(
        self,
        deletion_log: DeletionLog,
        service: str,
        status: ServiceSyncStatus,
        details: Optional[str] = None,
        error_message: Optional[str] = None,
        api_response: Optional[str] = None,
    ) -> DeletionSyncEvent:
        """Add a sync event to the deletion log."""
        event = DeletionSyncEvent(
            deletion_log_id=deletion_log.id,
            service=service,
            status=status,
            details=details,
            error_message=error_message,
            api_response=api_response,
            timestamp=datetime.utcnow(),
        )
        self.db.add(event)
        await self.db.flush()
        return event

    def _determine_services(
        self,
        request: MediaRequest,
        skip_services: list[str],
    ) -> dict[str, dict]:
        """
        Determine ALL services and their applicability for sync timeline.

        Returns dict with service info:
        {
            "radarr": {"applicable": True, "has_id": True, "skip": False},
            "sonarr": {"applicable": False, "has_id": False, "skip": False},
            ...
        }
        """
        is_tv = request.media_type == MediaType.TV
        is_movie = request.media_type == MediaType.MOVIE

        services = {
            # Sonarr only for TV shows
            "sonarr": {
                "applicable": is_tv,
                "has_id": request.sonarr_id is not None,
                "skip": "sonarr" in skip_services,
            },
            # Radarr only for movies
            "radarr": {
                "applicable": is_movie,
                "has_id": request.radarr_id is not None,
                "skip": "radarr" in skip_services,
            },
            # Shoko for anime content (check is_anime flag, not just shoko_series_id)
            # Shoko may have entries even without shoko_series_id being tracked
            "shoko": {
                "applicable": request.is_anime,
                "has_id": True,  # Shoko uses RemoveMissingFiles scan, doesn't need specific ID
                "skip": "shoko" in skip_services,
            },
            # Jellyfin always applicable
            "jellyfin": {
                "applicable": True,
                "has_id": request.jellyfin_id is not None,
                "skip": "jellyfin" in skip_services,
            },
            # Jellyseerr always applicable
            "jellyseerr": {
                "applicable": True,
                "has_id": request.jellyseerr_id is not None,
                "skip": "jellyseerr" in skip_services,
            },
        }

        return services

    def _get_services_to_sync(self, services_info: dict[str, dict]) -> list[str]:
        """Get list of services that should actually be synced (have IDs and are applicable)."""
        return [
            name for name, info in services_info.items()
            if info["applicable"] and info["has_id"] and not info["skip"]
        ]

    async def _sync_external_services(
        self,
        deletion_log: DeletionLog,
        services: list[str],
        delete_files: bool,
    ):
        """Sync deletion to external services."""
        # Order: Sonarr/Radarr first (deletes files), then Shoko, Jellyfin, Jellyseerr
        ordered_services = []
        if "sonarr" in services:
            ordered_services.append("sonarr")
        if "radarr" in services:
            ordered_services.append("radarr")
        if "shoko" in services:
            ordered_services.append("shoko")
        if "jellyfin" in services:
            ordered_services.append("jellyfin")
        if "jellyseerr" in services:
            ordered_services.append("jellyseerr")

        for service in ordered_services:
            await self._sync_service(deletion_log, service, delete_files)
            await self._broadcast_deletion_progress(deletion_log, service)

        # Check if all done
        await self._check_completion(deletion_log)

    async def _sync_service(
        self,
        deletion_log: DeletionLog,
        service: str,
        delete_files: bool,
    ):
        """Sync deletion to a single service."""
        # Mark as acknowledged
        await self._add_sync_event(
            deletion_log=deletion_log,
            service=service,
            status=ServiceSyncStatus.ACKNOWLEDGED,
            details=f"Sending DELETE request to {service}",
        )
        await self.db.commit()

        success = False
        message = ""

        try:
            if service == "sonarr" and deletion_log.sonarr_id:
                success, message = await sonarr_client.delete_series(
                    deletion_log.sonarr_id, delete_files=delete_files
                )
            elif service == "radarr" and deletion_log.radarr_id:
                success, message = await radarr_client.delete_movie(
                    deletion_log.radarr_id, delete_files=delete_files
                )
            elif service == "shoko" and deletion_log.is_anime:
                if delete_files:
                    # Trigger Shoko to scan and remove missing file entries
                    success, message = await shoko_http_client.remove_missing_files()
                else:
                    # Files kept on disk - skip Shoko
                    await self._add_sync_event(
                        deletion_log=deletion_log,
                        service=service,
                        status=ServiceSyncStatus.SKIPPED,
                        details="Files retained on disk - Shoko unchanged",
                    )
                    await self.db.commit()
                    return
            elif service == "jellyfin" and deletion_log.jellyfin_id:
                if delete_files:
                    # Files being deleted - trigger scan so Jellyfin removes entry
                    success, message = await jellyfin_client.delete_item(
                        deletion_log.jellyfin_id
                    )
                else:
                    # Files kept on disk - skip Jellyfin (nothing to remove)
                    await self._add_sync_event(
                        deletion_log=deletion_log,
                        service=service,
                        status=ServiceSyncStatus.SKIPPED,
                        details="Files retained on disk - Jellyfin unchanged",
                    )
                    await self.db.commit()
                    return  # Early return - don't go through normal success/fail flow
            elif service == "jellyseerr":
                # Jellyseerr has two entities: requests (who asked for it) and media (availability).
                # We need to delete both to fully clear the "Available" status.
                messages = []

                # Step 1: Delete the request record (if we have the ID)
                if deletion_log.jellyseerr_id:
                    req_success, req_msg = await jellyseerr_client.delete_request(
                        deletion_log.jellyseerr_id
                    )
                    messages.append(f"Request: {req_msg}")
                else:
                    req_success = True
                    messages.append("Request: No ID (skipped)")

                # Step 2: Delete the media entry to clear "Available" status
                # Look up by TMDB ID since we don't store mediaInfo.id
                media_type_str = "movie" if deletion_log.media_type == MediaType.MOVIE else "tv"
                media_id = await jellyseerr_client.get_media_id_by_tmdb(
                    deletion_log.tmdb_id, media_type_str
                )
                if media_id:
                    media_success, media_msg = await jellyseerr_client.delete_media(media_id)
                    messages.append(f"Media: {media_msg}")
                else:
                    media_success = True
                    messages.append("Media: No entry found (already cleared)")

                success = req_success and media_success
                message = "; ".join(messages)
            else:
                success = True
                message = "No ID available for this service"

        except Exception as e:
            success = False
            message = f"Exception: {e}"
            logger.exception(f"Error syncing deletion to {service}")

        # Mark result
        if success:
            await self._add_sync_event(
                deletion_log=deletion_log,
                service=service,
                status=ServiceSyncStatus.CONFIRMED,
                details=message,
            )
        else:
            await self._add_sync_event(
                deletion_log=deletion_log,
                service=service,
                status=ServiceSyncStatus.FAILED,
                error_message=message,
            )

        await self.db.commit()

    async def _check_completion(self, deletion_log: DeletionLog):
        """Check if all services are done and update status."""
        await self._update_deletion_status(deletion_log)

    async def _update_deletion_status(self, deletion_log: DeletionLog):
        """Calculate and update the overall deletion status based on sync events."""
        # Refresh to get latest sync events
        await self.db.refresh(deletion_log, ["sync_events"])

        # Get latest status for each service (last event wins)
        service_statuses = {}
        for event in deletion_log.sync_events:
            service_statuses[event.service] = event.status

        # Terminal states that mean "done" (success or appropriately skipped)
        success_states = {
            ServiceSyncStatus.CONFIRMED,
            ServiceSyncStatus.VERIFIED,
            ServiceSyncStatus.SKIPPED,
            ServiceSyncStatus.NOT_NEEDED,
            ServiceSyncStatus.NOT_APPLICABLE,
        }

        # States that mean "still in progress"
        in_progress_states = {
            ServiceSyncStatus.PENDING,
            ServiceSyncStatus.ACKNOWLEDGED,
        }

        # Check status
        has_failed = any(
            status == ServiceSyncStatus.FAILED
            for status in service_statuses.values()
        )
        has_in_progress = any(
            status in in_progress_states
            for status in service_statuses.values()
        )

        # Determine overall status
        if has_in_progress:
            deletion_log.status = DeletionStatus.IN_PROGRESS
        elif has_failed:
            deletion_log.status = DeletionStatus.INCOMPLETE
            deletion_log.completed_at = datetime.utcnow()
        else:
            # All services are in success states
            deletion_log.status = DeletionStatus.COMPLETE
            deletion_log.completed_at = datetime.utcnow()

        await self.db.commit()
        logger.info(f"Deletion {deletion_log.id} status: {deletion_log.status.value}")

    async def _broadcast_deletion_started(
        self,
        deletion_log: DeletionLog,
        services: list[str],
    ):
        """Broadcast deletion started event."""
        await broadcaster.broadcast("deletion_started", {
            "deletion_log_id": deletion_log.id,
            "title": deletion_log.title,
            "services_to_sync": services,
        })

    async def _broadcast_deletion_progress(
        self,
        deletion_log: DeletionLog,
        service: str,
    ):
        """Broadcast deletion progress event."""
        # Get latest status for this service
        await self.db.refresh(deletion_log, ["sync_events"])
        latest_event = None
        for event in deletion_log.sync_events:
            if event.service == service:
                latest_event = event

        if latest_event:
            await broadcaster.broadcast("deletion_progress", {
                "deletion_log_id": deletion_log.id,
                "service": service,
                "status": latest_event.status.value,
                "details": latest_event.details,
                "timestamp": latest_event.timestamp.isoformat(),
            })

    async def _broadcast_deletion_completed(self, deletion_log: DeletionLog):
        """Broadcast deletion completed event."""
        await self.db.refresh(deletion_log, ["sync_events"])

        await broadcaster.broadcast("deletion_completed", {
            "deletion_log_id": deletion_log.id,
            "status": deletion_log.status.value,
            "all_verified": deletion_log.status == DeletionStatus.COMPLETE,
            "completed_at": deletion_log.completed_at.isoformat() if deletion_log.completed_at else None,
        })

    async def preview_deletion(self, request_id: int) -> Optional[dict]:
        """
        Preview what would be deleted without actually deleting.

        Useful for confirmation dialogs.
        """
        request = await self._get_request(request_id)
        if not request:
            return None

        services_info = self._determine_services(request, [])
        services_to_sync = self._get_services_to_sync(services_info)

        # Extract year from title if not set
        year = request.year or extract_year_from_title(request.title)

        return {
            "request_id": request.id,
            "title": request.title,
            "media_type": request.media_type.value,
            "poster_url": request.poster_url,
            "year": year,
            "services_to_sync": services_to_sync,
            "services_info": services_info,  # Full info for each service
            "has_sonarr_id": request.sonarr_id is not None,
            "has_radarr_id": request.radarr_id is not None,
            "has_jellyfin_id": request.jellyfin_id is not None,
            "has_jellyseerr_id": request.jellyseerr_id is not None,
            "has_shoko_id": request.shoko_series_id is not None,
        }


async def delete_request(
    db: AsyncSession,
    request_id: int,
    user_id: Optional[str] = None,
    username: Optional[str] = None,
    delete_files: bool = True,
    source: DeletionSource = DeletionSource.DASHBOARD,
    skip_services: Optional[list[str]] = None,
) -> Optional[DeletionLog]:
    """
    Convenience function for deletion.

    Usage:
        from app.services.deletion_orchestrator import delete_request

        async with async_session() as db:
            result = await delete_request(db, request_id=123, user_id="abc")
    """
    orchestrator = DeletionOrchestrator(db)
    return await orchestrator.delete_request(
        request_id=request_id,
        user_id=user_id,
        username=username,
        delete_files=delete_files,
        source=source,
        skip_services=skip_services,
    )
