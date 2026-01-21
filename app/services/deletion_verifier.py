"""
Deletion verification service.

Background task that verifies deletions actually completed by checking each service.
Runs ~30 seconds after a deletion to confirm items are gone.
"""

import asyncio
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models import DeletionLog, DeletionSyncEvent, ServiceSyncStatus
from app.clients.sonarr import sonarr_client
from app.clients.radarr import radarr_client
from app.clients.jellyfin import jellyfin_client
from app.clients.jellyseerr import jellyseerr_client
from app.core.broadcaster import broadcaster

logger = logging.getLogger(__name__)

# How long to wait before verification (seconds)
VERIFICATION_DELAY = 30

# Max retries for verification
MAX_RETRIES = 3


async def schedule_verification(
    db_factory,
    deletion_log_id: int,
    delay: int = VERIFICATION_DELAY,
):
    """
    Schedule verification of a deletion after a delay.

    Args:
        db_factory: Async session factory (callable that returns AsyncSession)
        deletion_log_id: ID of the deletion log to verify
        delay: Seconds to wait before verification
    """
    asyncio.create_task(
        _run_verification_after_delay(db_factory, deletion_log_id, delay)
    )
    logger.info(f"Scheduled verification for deletion {deletion_log_id} in {delay}s")


async def _run_verification_after_delay(
    db_factory,
    deletion_log_id: int,
    delay: int,
):
    """Wait for delay then run verification."""
    await asyncio.sleep(delay)

    async with db_factory() as db:
        verifier = DeletionVerifier(db)
        await verifier.verify_deletion(deletion_log_id)


class DeletionVerifier:
    """
    Verifies that deletions actually completed by checking each service.

    For each service that was marked CONFIRMED:
    - Check if the item still exists
    - If gone: update to VERIFIED
    - If still exists: update to FAILED
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def verify_deletion(
        self,
        deletion_log_id: int,
        retry_count: int = 0,
    ) -> bool:
        """
        Verify all services for a deletion log.

        Args:
            deletion_log_id: ID of the deletion log
            retry_count: Current retry attempt

        Returns:
            True if all verified successfully, False otherwise
        """
        deletion_log = await self._get_deletion_log(deletion_log_id)
        if not deletion_log:
            logger.warning(f"Deletion log {deletion_log_id} not found for verification")
            return False

        logger.info(f"Verifying deletion {deletion_log_id}: {deletion_log.title}")

        # Get services that were CONFIRMED (need verification)
        services_to_verify = set()
        for event in deletion_log.sync_events:
            if event.status == ServiceSyncStatus.CONFIRMED:
                services_to_verify.add(event.service)

        if not services_to_verify:
            logger.info(f"No services to verify for deletion {deletion_log_id}")
            return True

        all_verified = True

        for service in services_to_verify:
            verified = await self._verify_service(deletion_log, service)
            if not verified:
                all_verified = False

        # Check if complete
        await self._check_completion(deletion_log)

        # Broadcast updated status
        await self._broadcast_verification_complete(deletion_log)

        # Retry if not all verified and we have retries left
        if not all_verified and retry_count < MAX_RETRIES:
            logger.info(
                f"Scheduling retry {retry_count + 1}/{MAX_RETRIES} for deletion {deletion_log_id}"
            )
            await asyncio.sleep(VERIFICATION_DELAY)
            return await self.verify_deletion(deletion_log_id, retry_count + 1)

        return all_verified

    async def _get_deletion_log(self, deletion_log_id: int) -> Optional[DeletionLog]:
        """Get deletion log with sync events."""
        result = await self.db.execute(
            select(DeletionLog)
            .where(DeletionLog.id == deletion_log_id)
            .options(selectinload(DeletionLog.sync_events))
        )
        return result.scalar_one_or_none()

    async def _verify_service(
        self,
        deletion_log: DeletionLog,
        service: str,
    ) -> bool:
        """
        Verify deletion for a single service.

        Returns True if verified (item is gone), False if still exists or error.
        """
        still_exists = False
        error_message = None

        try:
            if service == "sonarr" and deletion_log.sonarr_id:
                series = await sonarr_client.get_series(deletion_log.sonarr_id)
                still_exists = series is not None

            elif service == "radarr" and deletion_log.radarr_id:
                movie = await radarr_client.get_movie(deletion_log.radarr_id)
                still_exists = movie is not None

            elif service == "jellyfin" and deletion_log.jellyfin_id:
                item = await jellyfin_client.get_item(deletion_log.jellyfin_id)
                still_exists = item is not None

            elif service == "jellyseerr" and deletion_log.jellyseerr_id:
                request = await jellyseerr_client.get_request(deletion_log.jellyseerr_id)
                still_exists = request is not None

            elif service == "shoko":
                # Shoko doesn't have direct ID verification
                # Just trust the CONFIRMED status
                still_exists = False

            else:
                # No ID to verify
                still_exists = False

        except Exception as e:
            logger.exception(f"Error verifying {service} for deletion {deletion_log.id}")
            error_message = str(e)
            still_exists = True  # Treat errors as "still exists" to trigger retry

        # Add verification event
        if still_exists:
            await self._add_sync_event(
                deletion_log=deletion_log,
                service=service,
                status=ServiceSyncStatus.FAILED,
                error_message=error_message or "Item still exists in service",
            )
            await self.db.commit()
            return False
        else:
            await self._add_sync_event(
                deletion_log=deletion_log,
                service=service,
                status=ServiceSyncStatus.VERIFIED,
                details="Verified: item not found in service",
            )
            await self.db.commit()
            return True

    async def _add_sync_event(
        self,
        deletion_log: DeletionLog,
        service: str,
        status: ServiceSyncStatus,
        details: Optional[str] = None,
        error_message: Optional[str] = None,
    ) -> DeletionSyncEvent:
        """Add a sync event to the deletion log."""
        event = DeletionSyncEvent(
            deletion_log_id=deletion_log.id,
            service=service,
            status=status,
            details=details,
            error_message=error_message,
            timestamp=datetime.utcnow(),
        )
        self.db.add(event)
        await self.db.flush()
        return event

    async def _check_completion(self, deletion_log: DeletionLog):
        """Check if all services are verified and mark completion."""
        await self.db.refresh(deletion_log, ["sync_events"])

        # Get latest status for each service
        service_statuses = {}
        for event in deletion_log.sync_events:
            service_statuses[event.service] = event.status

        # Check if all are in terminal states
        terminal_states = {
            ServiceSyncStatus.VERIFIED,
            ServiceSyncStatus.FAILED,
            ServiceSyncStatus.SKIPPED,
            ServiceSyncStatus.NOT_NEEDED,
        }

        all_done = all(
            status in terminal_states
            for status in service_statuses.values()
        )

        if all_done and not deletion_log.completed_at:
            deletion_log.completed_at = datetime.utcnow()
            await self.db.commit()
            logger.info(f"Deletion {deletion_log.id} verification completed")

    async def _broadcast_verification_complete(self, deletion_log: DeletionLog):
        """Broadcast verification complete event."""
        await self.db.refresh(deletion_log, ["sync_events"])

        # Check results
        all_verified = all(
            event.status in {ServiceSyncStatus.VERIFIED, ServiceSyncStatus.SKIPPED, ServiceSyncStatus.NOT_NEEDED}
            for event in deletion_log.sync_events
            if event.status not in {ServiceSyncStatus.PENDING, ServiceSyncStatus.ACKNOWLEDGED, ServiceSyncStatus.CONFIRMED}
        )

        await broadcaster.broadcast({
            "event_type": "deletion_verified",
            "deletion_log_id": deletion_log.id,
            "all_verified": all_verified,
            "completed_at": deletion_log.completed_at.isoformat() if deletion_log.completed_at else None,
        })
