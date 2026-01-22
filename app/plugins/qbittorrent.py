"""qBittorrent plugin - tracks download progress and completion.

qBittorrent integration uses two methods:
1. Polling: Adaptive polling (5s active, 30s idle) for download progress
2. Webhook: "Run on complete" script triggers completion (DOWNLOADED state)

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

Episode Tracking:
- For TV shows, all episodes in a season pack share the same qbit_hash
- When polling updates progress, both the request AND all matching episodes are updated
- Episode states are updated: GRABBING → DOWNLOADING → DOWNLOADED

Adaptive Polling:
- POLL_FAST (3s): When there are active downloads (GRABBING or DOWNLOADING)
- POLL_SLOW (15s): When no active downloads (idle)
"""

import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select, func
from sqlalchemy.orm import selectinload

from app.core.plugin_base import ServicePlugin
from app.core.correlator import correlator
from app.core.state_machine import state_machine
from app.clients.qbittorrent import (
    QBittorrentClient,
    format_speed,
    format_eta,
    format_size,
)
from app.models import MediaRequest, MediaType, RequestState, Episode, EpisodeState
from app.services.state_calculator import calculate_aggregate_state

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# Adaptive polling intervals
POLL_FAST = 3   # seconds when downloads active (was 5s, reduced for responsiveness)
POLL_SLOW = 15  # seconds when idle (was 30s, reduced for quicker detection)


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
        return [RequestState.DOWNLOADING, RequestState.DOWNLOADED]

    @property
    def correlation_fields(self) -> list[str]:
        return ["qbit_hash"]

    @property
    def requires_polling(self) -> bool:
        return True

    @property
    def poll_interval(self) -> int:
        return POLL_FAST  # Default minimum interval

    async def get_adaptive_poll_interval(self, db: "AsyncSession") -> int:
        """
        Return polling interval based on active downloads.

        Checks database for requests in GRABBING or DOWNLOADING state.
        Returns POLL_FAST (3s) if active downloads, POLL_SLOW (15s) if idle.
        """
        active_count = await db.scalar(
            select(func.count()).select_from(MediaRequest).where(
                MediaRequest.state.in_([RequestState.GRABBING, RequestState.DOWNLOADING])
            )
        )
        return POLL_FAST if active_count and active_count > 0 else POLL_SLOW

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

        # Find request by torrent hash (need eager loading for TV episodes)
        stmt = (
            select(MediaRequest)
            .options(selectinload(MediaRequest.episodes))
            .where(MediaRequest.qbit_hash == torrent_hash.upper())
        )
        result = await db.execute(stmt)
        request = result.scalar_one_or_none()

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

        # Update episode states for TV shows
        if request.media_type == MediaType.TV and request.episodes:
            for episode in request.episodes:
                if episode.state == EpisodeState.DOWNLOADING:
                    episode.state = EpisodeState.DOWNLOADED

        # Determine target state
        if request.media_type == MediaType.TV:
            target_state = calculate_aggregate_state(request)
        else:
            target_state = RequestState.DOWNLOADED

        await state_machine.transition(
            request,
            target_state,
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
        Updates progress for all requests in GRABBING or DOWNLOADING state
        that have a qbit_hash.

        For TV shows, also updates Episode states.
        """
        updated_requests = []

        # Find all requests that should be tracked (with eager loaded episodes)
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
        """Get requests that should be tracked for download progress.

        Eager loads episodes for TV shows to update their states.
        """
        stmt = (
            select(MediaRequest)
            .options(selectinload(MediaRequest.episodes))
            .where(
                MediaRequest.state.in_([RequestState.GRABBING, RequestState.DOWNLOADING]),
                MediaRequest.qbit_hash.isnot(None),
            )
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

        For TV shows, also updates Episode states.

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
        if request.state == RequestState.GRABBING and is_downloading:
            # Update episode states for TV shows
            if request.media_type == MediaType.TV and request.episodes:
                for episode in request.episodes:
                    if episode.state == EpisodeState.GRABBING:
                        episode.state = EpisodeState.DOWNLOADING

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
                # Update episode states for TV shows
                if request.media_type == MediaType.TV and request.episodes:
                    for episode in request.episodes:
                        if episode.state == EpisodeState.DOWNLOADING:
                            episode.state = EpisodeState.DOWNLOADED

                # For TV, use aggregate state; for movies, use DOWNLOADED directly
                if request.media_type == MediaType.TV:
                    target_state = calculate_aggregate_state(request)
                else:
                    target_state = RequestState.DOWNLOADED

                await state_machine.transition(
                    request,
                    target_state,
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
