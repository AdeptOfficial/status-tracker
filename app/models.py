"""SQLAlchemy ORM models for request tracking."""

import enum
from datetime import datetime
from typing import Optional, TYPE_CHECKING

from sqlalchemy import String, Integer, DateTime, Enum, ForeignKey, Text, Float, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

if TYPE_CHECKING:
    from typing import List


class RequestState(str, enum.Enum):
    """
    States a media request can be in.
    Order roughly follows the lifecycle:
    REQUESTED -> APPROVED -> GRABBING -> DOWNLOADING -> DOWNLOADED -> IMPORTING -> [ANIME_MATCHING] -> AVAILABLE
    """

    REQUESTED = "requested"  # Initial request in Jellyseerr
    APPROVED = "approved"  # Request approved, waiting for grab
    GRABBING = "grabbing"  # Sonarr/Radarr grabbed from indexer (was INDEXED)
    DOWNLOADING = "downloading"  # qBittorrent actively downloading
    DOWNLOADED = "downloaded"  # Download complete, waiting for import (was DOWNLOAD_DONE)
    IMPORTING = "importing"  # Sonarr/Radarr importing to library
    ANIME_MATCHING = "anime_matching"  # Shoko matching anime metadata
    AVAILABLE = "available"  # Ready to watch in Jellyfin
    FAILED = "failed"  # Something went wrong
    TIMEOUT = "timeout"  # Stuck in a state too long
    MATCH_FAILED = "match_failed"  # Shoko couldn't match, needs manual intervention

    # Aliases for backward compatibility during migration
    INDEXED = "grabbing"  # Deprecated: use GRABBING
    DOWNLOAD_DONE = "downloaded"  # Deprecated: use DOWNLOADED


class EpisodeState(str, enum.Enum):
    """
    States an individual episode can be in.
    Similar to RequestState but without REQUESTED/APPROVED (episodes are created at grab).
    """

    GRABBING = "grabbing"  # Sonarr grabbed, qBit queued
    DOWNLOADING = "downloading"  # qBit actively downloading
    DOWNLOADED = "downloaded"  # qBit complete, waiting for import
    IMPORTING = "importing"  # Sonarr importing to library
    ANIME_MATCHING = "anime_matching"  # Shoko matching (anime only)
    AVAILABLE = "available"  # In Jellyfin, ready to watch
    FAILED = "failed"  # Error occurred
    MATCH_FAILED = "match_failed"  # Episode file needs manual linking in Shoko


class DeletionSource(str, enum.Enum):
    """Source of a media deletion."""

    DASHBOARD = "dashboard"  # Deleted via status-tracker UI
    SONARR = "sonarr"  # Detected via Sonarr webhook
    RADARR = "radarr"  # Detected via Radarr webhook
    JELLYFIN = "jellyfin"  # Detected via Jellyfin webhook
    SHOKO = "shoko"  # Detected via Shoko SignalR
    EXTERNAL = "external"  # Unknown source, detected via sync check


class ServiceSyncStatus(str, enum.Enum):
    """Status of sync operation for a specific service."""

    PENDING = "pending"  # Not yet attempted
    ACKNOWLEDGED = "acknowledged"  # API call sent, waiting for response
    CONFIRMED = "confirmed"  # API returned success
    VERIFIED = "verified"  # CLI check confirmed deletion
    FAILED = "failed"  # API returned error
    SKIPPED = "skipped"  # Deletion sync disabled
    NOT_NEEDED = "not_needed"  # Service didn't have this item (no ID)
    NOT_APPLICABLE = "not_applicable"  # Service doesn't apply (e.g., Sonarr for movies)


class DeletionStatus(str, enum.Enum):
    """Overall status of a deletion operation."""

    IN_PROGRESS = "in_progress"  # Deletion started, services being synced
    COMPLETE = "complete"  # All applicable services succeeded
    INCOMPLETE = "incomplete"  # At least one service failed


class MediaType(str, enum.Enum):
    """Type of media being requested."""

    MOVIE = "movie"
    TV = "tv"


class MediaRequest(Base):
    """
    Tracks a single media request through its lifecycle.

    Correlation fields allow matching events across services:
    - jellyseerr_id: From initial request
    - tmdb_id: Common across most services
    - tvdb_id: Used by Sonarr for TV
    - qbit_hash: Torrent hash for download tracking
    """

    __tablename__ = "requests"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Basic info
    title: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType))
    state: Mapped[RequestState] = mapped_column(
        Enum(RequestState), default=RequestState.REQUESTED
    )

    # Correlation IDs (used to match events across services)
    jellyseerr_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    tvdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    imdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # From Radarr/Sonarr Grab
    qbit_hash: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )

    # Service-specific IDs (for deletion API calls)
    sonarr_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Sonarr series ID
    radarr_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Radarr movie ID
    shoko_series_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Shoko series ID

    # Anime detection flag (set at Grab time from movie.tags or series.type)
    is_anime: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True, default=None)

    # Alternate titles (JSON array string) - for Shoko matching with Japanese titles
    alternate_titles: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Match failure info (for user notification in dashboard)
    match_failure_reason: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Download info (populated during DOWNLOADING)
    download_progress: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    download_speed: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # e.g., "5.2 MB/s"
    download_eta: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # e.g., "2h 15m"

    # Quality/source info (populated on GRABBING)
    quality: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., "WEBDL-1080p"
    indexer: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., "1337x"

    # Release info from Grab webhook
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # bytes
    release_group: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # File info (populated on IMPORTING)
    download_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    final_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Jellyfin info (populated on AVAILABLE)
    jellyfin_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Request metadata
    requested_by: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # Username
    poster_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # From Jellyseerr message

    # For TV: season/episode info (legacy - use Episode table for per-episode tracking)
    season: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    episode: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # TV-specific (new per-episode tracking)
    requested_seasons: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "1" or "1,2,3"
    total_episodes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Count of Episode rows

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    state_changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    available_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When reached AVAILABLE
    vfs_rebuild_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # Last Shokofin VFS rebuild attempt

    # Relationships
    timeline_events: Mapped[list["TimelineEvent"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="TimelineEvent.timestamp"
    )
    episodes: Mapped[list["Episode"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="Episode.season_number, Episode.episode_number"
    )


class TimelineEvent(Base):
    """
    Individual event in a request's timeline.
    Each state change or significant event creates a new entry.
    """

    __tablename__ = "timeline_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)

    # Event info
    service: Mapped[str] = mapped_column(String(50))  # e.g., "jellyseerr", "sonarr"
    event_type: Mapped[str] = mapped_column(String(100))  # e.g., "Grab", "Download"
    state: Mapped[RequestState] = mapped_column(Enum(RequestState))

    # Human-readable details
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Raw event data for debugging
    raw_data: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    request: Mapped["MediaRequest"] = relationship(back_populates="timeline_events")


class DeletionLog(Base):
    """
    Audit log for deleted media with per-service sync tracking.

    When a request is hard-deleted from the requests table, a DeletionLog
    entry preserves the audit trail. This includes what was deleted, who
    initiated it, and the sync status for each external service.
    """

    __tablename__ = "deletion_logs"

    id: Mapped[int] = mapped_column(primary_key=True)

    # Snapshot of what was deleted (copied from request before deletion)
    title: Mapped[str] = mapped_column(String(500))
    media_type: Mapped[MediaType] = mapped_column(Enum(MediaType))
    tmdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tvdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    jellyfin_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    sonarr_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    radarr_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    shoko_series_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    jellyseerr_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    qbit_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    poster_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_anime: Mapped[bool] = mapped_column(Boolean, default=False)  # For Shoko sync determination

    # Who/what initiated deletion
    source: Mapped[DeletionSource] = mapped_column(Enum(DeletionSource))
    deleted_by_user_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Jellyfin user ID
    deleted_by_username: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)  # Resolved username

    # Status tracking
    status: Mapped[DeletionStatus] = mapped_column(
        Enum(DeletionStatus), default=DeletionStatus.IN_PROGRESS
    )

    # Timestamps
    initiated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)  # When ALL services confirmed

    # Relationships
    sync_events: Mapped[list["DeletionSyncEvent"]] = relationship(
        back_populates="deletion_log", cascade="all, delete-orphan", order_by="DeletionSyncEvent.timestamp"
    )


class DeletionSyncEvent(Base):
    """
    Individual service sync event in deletion timeline.

    Tracks the status progression for each service during deletion:
    PENDING -> ACKNOWLEDGED -> CONFIRMED -> VERIFIED (or FAILED/SKIPPED)
    """

    __tablename__ = "deletion_sync_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    deletion_log_id: Mapped[int] = mapped_column(ForeignKey("deletion_logs.id"), index=True)

    # Which service
    service: Mapped[str] = mapped_column(String(50))  # "jellyfin", "sonarr", "radarr", "shoko", "jellyseerr"

    # Status progression
    status: Mapped[ServiceSyncStatus] = mapped_column(Enum(ServiceSyncStatus))

    # Details
    details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Human-readable message
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # If failed, why
    api_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Raw API response (JSON)

    # Timestamp
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    deletion_log: Mapped["DeletionLog"] = relationship(back_populates="sync_events")


class Episode(Base):
    """
    Individual episode tracking for TV shows.

    Created at Grab time from Sonarr webhook episodes[] array.
    Season packs: all episodes share the same qbit_hash.
    Individual grabs: each episode may have a different qbit_hash.
    """

    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)

    # Episode identification
    season_number: Mapped[int] = mapped_column(Integer)
    episode_number: Mapped[int] = mapped_column(Integer)
    episode_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # From Sonarr Grab webhook

    # Service IDs (from Sonarr Grab webhook)
    sonarr_episode_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    episode_tvdb_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # State tracking
    state: Mapped[EpisodeState] = mapped_column(Enum(EpisodeState), default=EpisodeState.GRABBING)

    # Download tracking (shared for season packs)
    qbit_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # File path (from Sonarr Import webhook)
    final_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Anime matching (from Shoko)
    shoko_file_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Jellyfin (from verification)
    jellyfin_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    # Relationships
    request: Mapped["MediaRequest"] = relationship(back_populates="episodes")
