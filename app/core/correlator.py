"""Event correlation engine.

Matches incoming events from different services to existing requests using
various ID fields (tmdb_id, tvdb_id, jellyseerr_id, qbit_hash).

The challenge: Different services use different IDs.
- Jellyseerr: jellyseerr_id, tmdb_id
- Sonarr: tvdb_id, download hash
- Radarr: tmdb_id, download hash
- qBittorrent: hash
- Jellyfin: tmdb_id, tvdb_id (via provider IDs)
"""

import logging
from typing import TYPE_CHECKING, Optional

from sqlalchemy import select, or_

from app.models import MediaRequest, RequestState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# States that are considered "active" (not terminal)
# NOTE: AVAILABLE is intentionally NOT in this list to prevent matching old requests
# when a new request comes in for the same media.
ACTIVE_STATES = [
    RequestState.REQUESTED,
    RequestState.APPROVED,
    RequestState.GRABBING,
    RequestState.DOWNLOADING,
    RequestState.DOWNLOADED,
    RequestState.IMPORTING,
    RequestState.ANIME_MATCHING,
]


class EventCorrelator:
    """
    Matches events to existing requests using correlation IDs.

    Usage:
        correlator = EventCorrelator()
        request = await correlator.find_by_tmdb(db, 12345)
        request = await correlator.find_by_hash(db, "abc123...")
    """

    async def find_by_jellyseerr_id(
        self, db: "AsyncSession", jellyseerr_id: int
    ) -> Optional[MediaRequest]:
        """Find active request by Jellyseerr request ID."""
        stmt = select(MediaRequest).where(
            MediaRequest.jellyseerr_id == jellyseerr_id,
            MediaRequest.state.in_(ACTIVE_STATES + [RequestState.AVAILABLE]),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_tmdb(
        self, db: "AsyncSession", tmdb_id: int
    ) -> Optional[MediaRequest]:
        """Find active request by TMDB ID (movies and some TV)."""
        stmt = select(MediaRequest).where(
            MediaRequest.tmdb_id == tmdb_id,
            MediaRequest.state.in_(ACTIVE_STATES),
        ).order_by(MediaRequest.created_at.desc())
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_tvdb(
        self, db: "AsyncSession", tvdb_id: int
    ) -> Optional[MediaRequest]:
        """Find active request by TVDB ID (TV shows via Sonarr)."""
        stmt = select(MediaRequest).where(
            MediaRequest.tvdb_id == tvdb_id,
            MediaRequest.state.in_(ACTIVE_STATES),
        ).order_by(MediaRequest.created_at.desc())
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_hash(
        self, db: "AsyncSession", qbit_hash: str
    ) -> Optional[MediaRequest]:
        """Find active request by qBittorrent hash (download tracking).

        Filters to active states to avoid matching old completed requests
        if the same torrent is re-downloaded.
        """
        if not qbit_hash:
            return None
        # Hash matching is case-insensitive, filtered to active states
        stmt = select(MediaRequest).where(
            MediaRequest.qbit_hash.ilike(qbit_hash),
            MediaRequest.state.in_(ACTIVE_STATES),
        ).order_by(MediaRequest.created_at.desc())
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_any(
        self, db: "AsyncSession", tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None, jellyseerr_id: Optional[int] = None,
        qbit_hash: Optional[str] = None, season: Optional[int] = None,
    ) -> Optional[MediaRequest]:
        """Prefer exact IDs; require season identity for ambiguous TV requests."""
        from app.models import MediaType
        filters = []
        if qbit_hash:
            filters.append(MediaRequest.qbit_hash.ilike(qbit_hash))
        if jellyseerr_id:
            filters.append(MediaRequest.jellyseerr_id == jellyseerr_id)
        if tmdb_id:
            filters.append(MediaRequest.tmdb_id == tmdb_id)
        if tvdb_id:
            filters.append(MediaRequest.tvdb_id == tvdb_id)
        for condition in filters:
            stmt = select(MediaRequest).where(condition,
                MediaRequest.state.in_(ACTIVE_STATES + ([RequestState.AVAILABLE] if jellyseerr_id else [])))
            if season is not None:
                stmt = stmt.where(MediaRequest.media_type == MediaType.TV, or_(MediaRequest.season == season, MediaRequest.season.is_(None)))
            rows = list((await db.scalars(stmt)).all())
            if len(rows) == 1:
                return rows[0]
            # Never select an arbitrary season when provider IDs are shared.
            if len(rows) > 1:
                logger.warning("Ambiguous request correlation; season=%s", season)
                return None
        return None

    async def find_active_downloads(
        self, db: "AsyncSession"
    ) -> list[MediaRequest]:
        """Find all requests currently in DOWNLOADING state."""
        stmt = select(MediaRequest).where(
            MediaRequest.state == RequestState.DOWNLOADING,
            MediaRequest.qbit_hash.isnot(None),
        )
        result = await db.execute(stmt)
        return list(result.scalars().all())


# Global instance
correlator = EventCorrelator()
