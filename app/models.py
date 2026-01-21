"""SQLAlchemy ORM models for request tracking."""

import enum
from datetime import datetime
from typing import Optional

from sqlalchemy import String, Integer, DateTime, Enum, ForeignKey, Text, Float
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class RequestState(str, enum.Enum):
    """
    States a media request can be in.
    Order roughly follows the lifecycle:
    REQUESTED -> APPROVED -> INDEXED -> DOWNLOADING -> DOWNLOAD_DONE -> IMPORTING -> [ANIME_MATCHING] -> AVAILABLE
    """

    REQUESTED = "requested"  # Initial request in Jellyseerr
    APPROVED = "approved"  # Request approved, waiting for grab
    INDEXED = "indexed"  # Sonarr/Radarr grabbed from indexer
    DOWNLOADING = "downloading"  # qBittorrent actively downloading
    DOWNLOAD_DONE = "download_done"  # Download complete, waiting for import
    IMPORTING = "importing"  # Sonarr/Radarr importing to library
    ANIME_MATCHING = "anime_matching"  # Shoko matching anime metadata
    AVAILABLE = "available"  # Ready to watch in Jellyfin
    FAILED = "failed"  # Something went wrong
    TIMEOUT = "timeout"  # Stuck in a state too long


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
    qbit_hash: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True, index=True
    )

    # Service-specific IDs (for deletion API calls)
    sonarr_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Sonarr series ID
    radarr_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Radarr movie ID
    shoko_series_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)  # Shoko series ID

    # Download info (populated during DOWNLOADING)
    download_progress: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    download_speed: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # e.g., "5.2 MB/s"
    download_eta: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True
    )  # e.g., "2h 15m"

    # Quality/source info (populated on INDEXED)
    quality: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., "WEBDL-1080p"
    indexer: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )  # e.g., "1337x"

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

    # For TV: season/episode info
    season: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    episode: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )
    state_changed_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    timeline_events: Mapped[list["TimelineEvent"]] = relationship(
        back_populates="request", cascade="all, delete-orphan", order_by="TimelineEvent.timestamp"
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
    poster_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    year: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

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
