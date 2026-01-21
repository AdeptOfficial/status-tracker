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

from sqlalchemy import select

from app.models import MediaRequest, RequestState

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# States that are considered "active" (not terminal)
ACTIVE_STATES = [
    RequestState.REQUESTED,
    RequestState.APPROVED,
    RequestState.INDEXED,
    RequestState.DOWNLOADING,
    RequestState.DOWNLOAD_DONE,
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
        """Find request by qBittorrent hash (download tracking)."""
        if not qbit_hash:
            return None
        # Hash matching is case-insensitive
        stmt = select(MediaRequest).where(
            MediaRequest.qbit_hash.ilike(qbit_hash),
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_any(
        self,
        db: "AsyncSession",
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        jellyseerr_id: Optional[int] = None,
        qbit_hash: Optional[str] = None,
    ) -> Optional[MediaRequest]:
        """
        Find request using any available correlation ID.
        Tries IDs in order of specificity: hash > jellyseerr > tmdb > tvdb.
        """
        if qbit_hash:
            request = await self.find_by_hash(db, qbit_hash)
            if request:
                return request

        if jellyseerr_id:
            request = await self.find_by_jellyseerr_id(db, jellyseerr_id)
            if request:
                return request

        if tmdb_id:
            request = await self.find_by_tmdb(db, tmdb_id)
            if request:
                return request

        if tvdb_id:
            request = await self.find_by_tvdb(db, tvdb_id)
            if request:
                return request

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
