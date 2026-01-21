"""qBittorrent plugin - tracks download progress and completion.

qBittorrent integration uses two methods:
1. Polling: Check progress every 5s for active downloads (DOWNLOADING state)
2. Webhook: "Run on complete" script triggers completion (DOWNLOAD_DONE state)

Webhook setup in qBittorrent:
  Options -> Downloads -> "Run external program on torrent finished"
  Command:
    curl -X POST http://status-tracker:8000/hooks/qbittorrent \
      -H "Content-Type: application/json" \
      -d '{"hash": "%I", "name": "%N", "path": "%D/%N", "size": "%Z"}'

  Variables:
    %I = torrent hash
    %N = torrent name
    %D = save path
    %Z = torrent size
"""

import logging
from typing import TYPE_CHECKING, Optional

from app.core.plugin_base import ServicePlugin
from app.core.correlator import correlator
from app.core.state_machine import state_machine
from app.clients.qbittorrent import (
    QBittorrentClient,
    format_speed,
    format_eta,
    format_size,
)
from app.models import MediaRequest, RequestState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class QBittorrentPlugin(ServicePlugin):
    """Handles qBittorrent download tracking."""

    def __init__(self):
        self._client: Optional[QBittorrentClient] = None

    @property
    def name(self) -> str:
        return "qbittorrent"

    @property
    def display_name(self) -> str:
        return "qBittorrent"

    @property
    def states_provided(self) -> list[RequestState]:
        return [RequestState.DOWNLOADING, RequestState.DOWNLOAD_DONE]

    @property
    def correlation_fields(self) -> list[str]:
        return ["qbit_hash"]

    @property
    def requires_polling(self) -> bool:
        return True

    @property
    def poll_interval(self) -> int:
        return 5  # Check every 5 seconds

    async def _get_client(self) -> QBittorrentClient:
        """Get or create qBittorrent client."""
        if self._client is None:
            self._client = QBittorrentClient()
            await self._client.login()
        return self._client

    async def handle_webhook(
        self, payload: dict, db: "AsyncSession"
    ) -> Optional[MediaRequest]:
        """
        Handle "run on complete" webhook from qBittorrent.

        Expected payload (from curl command):
        {
            "hash": "ABC123DEF456...",
            "name": "Movie.Name.2022.1080p.BluRay",
            "path": "/data/downloads/complete/Movie.Name.2022.1080p.BluRay",
            "size": "1234567890"
        }
        """
        torrent_hash = payload.get("hash", "")
        torrent_name = payload.get("name", "")
        torrent_path = payload.get("path", "")

        if not torrent_hash:
            logger.warning("qBittorrent webhook missing hash")
            return None

        logger.info(f"qBittorrent complete webhook: {torrent_name} ({torrent_hash[:8]}...)")

        # Find request by torrent hash
        request = await correlator.find_by_hash(db, torrent_hash)

        if not request:
            logger.debug(f"No matching request found for hash {torrent_hash[:8]}...")
            return None

        # Store download path
        if torrent_path:
            request.download_path = torrent_path

        # Mark as 100% complete
        request.download_progress = 1.0
        request.download_speed = None
        request.download_eta = None

        await state_machine.transition(
            request,
            RequestState.DOWNLOAD_DONE,
            db,
            service=self.name,
            event_type="Complete",
            details=f"Download complete: {torrent_name}",
            raw_data=payload,
        )

        logger.info(f"Download complete: {request.title}")
        return request

    async def poll(self, db: "AsyncSession") -> list[MediaRequest]:
        """
        Poll qBittorrent for download progress updates.

        Called every poll_interval seconds.
        Updates progress for all requests in INDEXED or DOWNLOADING state
        that have a qbit_hash.
        """
        updated_requests = []

        # Find all requests that should be tracked
        # INDEXED: Waiting for download to start
        # DOWNLOADING: Already downloading, need progress updates
        active_requests = await self._get_trackable_requests(db)

        if not active_requests:
            return []

        # Get hashes to query
        hashes = [r.qbit_hash for r in active_requests if r.qbit_hash]
        if not hashes:
            return []

        try:
            client = await self._get_client()
            torrents = await client.get_torrents(hashes=hashes)

            # Create a hash -> torrent lookup
            torrent_map = {t.hash.lower(): t for t in torrents}

            for request in active_requests:
                if not request.qbit_hash:
                    continue

                torrent = torrent_map.get(request.qbit_hash.lower())
                if not torrent:
                    continue

                updated = await self._update_request_progress(request, torrent, db)
                if updated:
                    updated_requests.append(request)

        except Exception as e:
            logger.error(f"Error polling qBittorrent: {e}")

        return updated_requests

    async def _get_trackable_requests(
        self, db: "AsyncSession"
    ) -> list[MediaRequest]:
        """Get requests that should be tracked for download progress."""
        from sqlalchemy import select
        from app.models import MediaRequest, RequestState

        stmt = select(MediaRequest).where(
            MediaRequest.state.in_([RequestState.INDEXED, RequestState.DOWNLOADING]),
            MediaRequest.qbit_hash.isnot(None),
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())

    async def _update_request_progress(
        self,
        request: MediaRequest,
        torrent,
        db: "AsyncSession",
    ) -> bool:
        """
        Update request with torrent progress.

        Returns True if request was updated.
        """
        # Check if download has started
        is_downloading = torrent.state in (
            "downloading",
            "stalledDL",
            "forcedDL",
            "metaDL",
            "queuedDL",
        )
        is_complete = torrent.state in ("uploading", "stalledUP", "forcedUP", "pausedUP")
        progress = torrent.progress

        # Update progress info
        old_progress = request.download_progress or 0
        request.download_progress = progress
        request.download_speed = format_speed(torrent.download_speed) if torrent.download_speed > 0 else None
        request.download_eta = format_eta(torrent.eta) if torrent.eta > 0 else None

        # Determine if state change needed
        if request.state == RequestState.INDEXED and is_downloading:
            # Transition to DOWNLOADING
            await state_machine.transition(
                request,
                RequestState.DOWNLOADING,
                db,
                service=self.name,
                event_type="Started",
                details=f"Downloading: {format_size(torrent.size)}",
                raw_data={"progress": progress, "state": torrent.state},
            )
            logger.info(f"Download started: {request.title}")
            return True

        elif request.state == RequestState.DOWNLOADING:
            # Check for completion
            if is_complete or progress >= 1.0:
                await state_machine.transition(
                    request,
                    RequestState.DOWNLOAD_DONE,
                    db,
                    service=self.name,
                    event_type="Complete",
                    details=f"Download complete: {format_size(torrent.downloaded)}",
                    raw_data={"progress": progress, "state": torrent.state},
                )
                logger.info(f"Download complete: {request.title}")
                return True

            # Progress update (only log significant changes)
            if abs(progress - old_progress) >= 0.05:  # 5% threshold
                logger.debug(
                    f"Download progress: {request.title} - "
                    f"{progress * 100:.1f}% ({request.download_speed})"
                )
                return True

        return False

    def get_timeline_details(self, event_data: dict) -> str:
        """Format event for timeline display."""
        progress = event_data.get("progress", 0)
        state = event_data.get("state", "")

        if state in ("uploading", "stalledUP"):
            return "Download complete"

        return f"{progress * 100:.0f}% complete"
