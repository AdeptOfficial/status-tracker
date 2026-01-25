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

Episode Tracking (Multi-Torrent Support):
- For TV shows, episodes are tracked by their individual qbit_hash
- Season packs: all episodes share the same qbit_hash
- Missing episodes grabbed separately: each batch has its own qbit_hash
- Polling queries ALL unique episode hashes, enabling multi-torrent tracking
- Episode states are updated: GRABBING → DOWNLOADING → DOWNLOADED
- Request state is aggregated from episode states

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

        # Find request by torrent hash - try request-level first (movies), then episode-level (TV)
        hash_upper = torrent_hash.upper()
        hash_lower = torrent_hash.lower()

        # Try 1: Find by request.qbit_hash (movies and legacy)
        stmt = (
            select(MediaRequest)
            .options(selectinload(MediaRequest.episodes))
            .where(MediaRequest.qbit_hash == hash_upper)
        )
        result = await db.execute(stmt)
        request = result.scalar_one_or_none()

        # Try 2: Find by episode.qbit_hash (TV multi-torrent)
        if not request:
            stmt = (
                select(Episode)
                .where(Episode.qbit_hash == hash_upper)
                .limit(1)
            )
            result = await db.execute(stmt)
            episode = result.scalar_one_or_none()
            if episode:
                # Load the request with all episodes
                stmt = (
                    select(MediaRequest)
                    .options(selectinload(MediaRequest.episodes))
                    .where(MediaRequest.id == episode.request_id)
                )
                result = await db.execute(stmt)
                request = result.scalar_one_or_none()
                logger.debug(f"Found request via episode hash: {request.title if request else 'None'}")

        if not request:
            logger.debug(f"No matching request found for hash {torrent_hash[:8]}...")
            return None

        # Store download path
        if torrent_path:
            request.download_path = torrent_path

        # Update episode states for TV shows (only episodes with THIS hash)
        if request.media_type == MediaType.TV and request.episodes:
            updated_count = 0
            for episode in request.episodes:
                # Only update episodes that have this specific hash
                if episode.qbit_hash and episode.qbit_hash.lower() == hash_lower:
                    if episode.state in (EpisodeState.GRABBING, EpisodeState.DOWNLOADING):
                        episode.state = EpisodeState.DOWNLOADED
                        updated_count += 1

            logger.debug(f"Marked {updated_count} episodes as DOWNLOADED for hash {torrent_hash[:8]}...")

            # Calculate download_progress from episode completion
            total_eps = len(request.episodes) or 1
            downloaded_eps = sum(
                1 for e in request.episodes
                if e.state in (EpisodeState.DOWNLOADED, EpisodeState.IMPORTING,
                              EpisodeState.ANIME_MATCHING, EpisodeState.AVAILABLE)
            )
            request.download_progress = downloaded_eps / total_eps
            target_state = calculate_aggregate_state(request)
        else:
            # Movies: mark as 100% complete
            request.download_progress = 1.0
            target_state = RequestState.DOWNLOADED

        request.download_speed = None
        request.download_eta = None

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
        For TV shows, tracks ALL episode hashes (supports multi-torrent scenarios
        like season pack + missing episodes grabbed separately).
        For movies, falls back to request-level hash tracking.
        """
        updated_requests = []

        # Get requests and hash-to-episode mapping
        requests, hash_to_episodes = await self._get_trackable_requests(db)

        if not requests:
            return []

        # Get ALL unique hashes to query (from episodes, not requests)
        hashes = list(hash_to_episodes.keys())

        # Also include request-level hashes for movies (they aren't in hash_to_episodes)
        for request in requests:
            if request.media_type == MediaType.MOVIE and request.qbit_hash:
                hash_key = request.qbit_hash.lower()
                if hash_key not in hashes:
                    hashes.append(hash_key)

        if not hashes:
            return []

        try:
            client = await self._get_client()
            torrents = await client.get_torrents(hashes=hashes)
            torrent_map = {t.hash.lower(): t for t in torrents}

            # Track which requests need state recalculation and their torrent data
            updated_request_ids: set[int] = set()
            request_torrents: dict[int, list] = {}  # request_id -> list of torrents

            # Update TV episode states from their individual hashes
            for hash_key, episodes in hash_to_episodes.items():
                torrent = torrent_map.get(hash_key)
                if not torrent:
                    continue

                for episode in episodes:
                    # Track torrent for this request (for progress aggregation)
                    if episode.request_id not in request_torrents:
                        request_torrents[episode.request_id] = []
                    if torrent not in request_torrents[episode.request_id]:
                        request_torrents[episode.request_id].append(torrent)

                    updated = await self._update_episode_progress(episode, torrent)
                    if updated:
                        updated_request_ids.add(episode.request_id)
                        logger.debug(
                            f"Episode S{episode.season_number:02d}E{episode.episode_number:02d} "
                            f"-> {episode.state.value} (hash: {hash_key[:8]}...)"
                        )

            # Recalculate request states and update progress from torrents
            for request in requests:
                if request.media_type == MediaType.TV:
                    # Update progress/speed/eta from torrent data
                    torrents_for_request = request_torrents.get(request.id, [])
                    if torrents_for_request:
                        await self._update_tv_progress_from_torrents(request, torrents_for_request)
                        updated_requests.append(request)

                    # Also recalculate state if episodes changed
                    if request.id in updated_request_ids:
                        await self._recalculate_request_state(request, db)
                else:
                    # Movies: use the original request-level tracking
                    if request.qbit_hash:
                        torrent = torrent_map.get(request.qbit_hash.lower())
                        if torrent:
                            updated = await self._update_request_progress(request, torrent, db)
                            if updated:
                                updated_requests.append(request)

        except Exception as e:
            logger.error(f"Error polling qBittorrent: {e}")

        return updated_requests

    async def _get_trackable_requests(
        self, db: "AsyncSession"
    ) -> tuple[list[MediaRequest], dict[str, list[Episode]]]:
        """Get requests that should be tracked, with hash-to-episode mapping.

        For TV shows, we track at the Episode level (each episode can have a
        different qbit_hash when grabbed separately). This enables tracking
        multiple torrents for the same request (e.g., season pack + missing eps).

        Returns:
            - List of requests in GRABBING/DOWNLOADING state
            - Dict mapping qbit_hash -> list of Episodes with that hash
        """
        stmt = (
            select(MediaRequest)
            .options(selectinload(MediaRequest.episodes))
            .where(
                MediaRequest.state.in_([RequestState.GRABBING, RequestState.DOWNLOADING]),
            )
        )
        result = await db.execute(stmt)
        requests = list(result.scalars().all())

        # Build hash -> episodes mapping from all episode-level hashes
        hash_to_episodes: dict[str, list[Episode]] = {}
        for request in requests:
            # For TV shows: track by episode hashes (supports multi-torrent)
            if request.media_type == MediaType.TV and request.episodes:
                for episode in request.episodes:
                    if episode.qbit_hash and episode.state in (EpisodeState.GRABBING, EpisodeState.DOWNLOADING):
                        hash_key = episode.qbit_hash.lower()
                        if hash_key not in hash_to_episodes:
                            hash_to_episodes[hash_key] = []
                        hash_to_episodes[hash_key].append(episode)
            # For movies: fall back to request-level hash
            elif request.qbit_hash:
                hash_key = request.qbit_hash.lower()
                if hash_key not in hash_to_episodes:
                    hash_to_episodes[hash_key] = []
                # Store None to indicate movie (no episode to update)

        return requests, hash_to_episodes

    async def _update_episode_progress(self, episode: Episode, torrent) -> bool:
        """Update single episode based on torrent state.

        Returns True if episode state changed.
        """
        is_downloading = torrent.state in (
            "downloading", "stalledDL", "forcedDL", "metaDL", "queuedDL"
        )
        is_complete = (
            torrent.state in ("uploading", "stalledUP", "forcedUP", "pausedUP")
            or torrent.progress >= 1.0
        )

        if episode.state == EpisodeState.GRABBING and is_downloading:
            episode.state = EpisodeState.DOWNLOADING
            return True

        if episode.state == EpisodeState.DOWNLOADING and is_complete:
            episode.state = EpisodeState.DOWNLOADED
            return True

        return False

    async def _update_tv_progress_from_torrents(
        self, request: MediaRequest, torrents: list
    ) -> None:
        """Update TV request progress/speed/eta from active torrents.

        Aggregates data across multiple torrents (for multi-torrent tracking).
        - progress: weighted average by torrent size
        - speed: sum of all torrent speeds
        - eta: max of all torrent ETAs
        """
        if not torrents:
            return

        total_size = sum(t.size for t in torrents if t.size) or 1
        weighted_progress = sum(
            t.progress * t.size for t in torrents if t.size
        ) / total_size

        total_speed = sum(t.download_speed for t in torrents if t.download_speed)
        max_eta = max((t.eta for t in torrents if t.eta and t.eta > 0), default=0)

        request.download_progress = weighted_progress
        request.download_speed = format_speed(total_speed) if total_speed > 0 else None
        request.download_eta = format_eta(max_eta) if max_eta > 0 else None

    async def _recalculate_request_state(
        self, request: MediaRequest, db: "AsyncSession"
    ) -> None:
        """Recalculate request state from episode aggregates.

        Only updates download_progress when transitioning OUT of downloading
        (to show episode completion ratio). During downloading, progress comes
        from _update_tv_progress_from_torrents() for live torrent %.
        """
        new_state = calculate_aggregate_state(request)

        total_eps = len(request.episodes) or 1
        downloaded_eps = sum(
            1 for e in request.episodes
            if e.state in (EpisodeState.DOWNLOADED, EpisodeState.IMPORTING,
                          EpisodeState.ANIME_MATCHING, EpisodeState.AVAILABLE)
        )

        # Only update download_progress when past DOWNLOADING state
        # During DOWNLOADING, torrent % is set by _update_tv_progress_from_torrents
        if new_state not in (RequestState.GRABBING, RequestState.DOWNLOADING):
            request.download_progress = downloaded_eps / total_eps

        # Only transition if state actually changed
        if new_state != request.state:
            await state_machine.transition(
                request, new_state, db,
                service=self.name,
                event_type="Aggregate",
                details=f"Episode aggregation: {downloaded_eps}/{total_eps} complete",
            )

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
            size_str = format_size(torrent.size) if torrent.size else ""
            await state_machine.transition(
                request,
                RequestState.DOWNLOADING,
                db,
                service=self.name,
                event_type="Started",
                details=f"Downloading: {request.title}" + (f" ({size_str})" if size_str else ""),
                raw_data={"progress": progress, "state": torrent.state, "size": torrent.size},
            )
            logger.info(f"Download started: {request.title} ({size_str})")
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

            # Log significant progress changes (5% threshold to reduce log spam)
            if abs(progress - old_progress) >= 0.05:
                logger.debug(
                    f"Download progress: {request.title} - "
                    f"{progress * 100:.1f}% ({request.download_speed})"
                )

            # Always broadcast progress updates for smooth UX
            # The 3s poll interval already throttles updates adequately
            return True

        return False

    def get_timeline_details(self, event_data: dict) -> str:
        """Format event for timeline display."""
        progress = event_data.get("progress", 0)
        state = event_data.get("state", "")

        if state in ("uploading", "stalledUP"):
            return "Download complete"

        return f"{progress * 100:.0f}% complete"
