"""Pydantic schemas for API responses and webhook payloads."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, field_validator

from app.models import RequestState, MediaType, DeletionSource, ServiceSyncStatus, DeletionStatus


# ============================================
# API Response Schemas
# ============================================


class TimelineEventResponse(BaseModel):
    """Single event in timeline."""

    id: int
    service: str
    event_type: str
    state: RequestState
    details: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class MediaRequestResponse(BaseModel):
    """Single media request for API response."""

    id: int
    title: str
    media_type: MediaType
    state: RequestState

    # IDs
    jellyseerr_id: Optional[int] = None
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    sonarr_id: Optional[int] = None
    radarr_id: Optional[int] = None
    shoko_series_id: Optional[int] = None

    # Download info
    download_progress: Optional[float] = None
    download_speed: Optional[str] = None
    download_eta: Optional[str] = None

    # Quality
    quality: Optional[str] = None
    indexer: Optional[str] = None

    # Metadata
    requested_by: Optional[str] = None
    poster_url: Optional[str] = None
    year: Optional[int] = None
    season: Optional[int] = None
    episode: Optional[int] = None

    # Jellyfin
    jellyfin_id: Optional[str] = None

    # Timestamps
    created_at: datetime
    updated_at: datetime
    state_changed_at: datetime

    # Convert empty strings to None for optional int fields
    @field_validator('jellyseerr_id', 'tmdb_id', 'tvdb_id', 'year', 'season', 'episode', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v

    class Config:
        from_attributes = True


class MediaRequestDetailResponse(MediaRequestResponse):
    """Media request with full timeline."""

    timeline_events: list[TimelineEventResponse] = []


class RequestListResponse(BaseModel):
    """Paginated list of requests."""

    requests: list[MediaRequestResponse]
    total: int
    page: int
    per_page: int


# ============================================
# Deletion Log Response Schemas
# ============================================


class DeletionSyncEventResponse(BaseModel):
    """Single sync event in deletion timeline."""

    id: int
    service: str
    status: ServiceSyncStatus
    details: Optional[str] = None
    error_message: Optional[str] = None
    timestamp: datetime

    class Config:
        from_attributes = True


class DeletionLogResponse(BaseModel):
    """Deletion audit log entry."""

    id: int
    title: str
    media_type: MediaType
    tmdb_id: Optional[int] = None
    tvdb_id: Optional[int] = None
    jellyfin_id: Optional[str] = None
    sonarr_id: Optional[int] = None
    radarr_id: Optional[int] = None
    shoko_series_id: Optional[int] = None
    jellyseerr_id: Optional[int] = None
    poster_url: Optional[str] = None
    year: Optional[int] = None

    source: DeletionSource
    deleted_by_user_id: Optional[str] = None
    deleted_by_username: Optional[str] = None
    status: DeletionStatus = DeletionStatus.IN_PROGRESS

    initiated_at: datetime
    completed_at: Optional[datetime] = None

    # Convert empty strings to None for optional int fields
    @field_validator('tmdb_id', 'tvdb_id', 'sonarr_id', 'radarr_id', 'shoko_series_id', 'jellyseerr_id', 'year', mode='before')
    @classmethod
    def empty_str_to_none(cls, v):
        if v == '' or v is None:
            return None
        return v

    class Config:
        from_attributes = True


class DeletionLogDetailResponse(DeletionLogResponse):
    """Deletion log with full sync event timeline."""

    sync_events: list[DeletionSyncEventResponse] = []


class DeletionLogListResponse(BaseModel):
    """Paginated list of deletion logs."""

    logs: list[DeletionLogResponse]
    total: int
    page: int
    per_page: int


class DeleteRequestPayload(BaseModel):
    """Payload for delete request endpoint."""

    delete_files: bool = True


class BulkDeleteRequestPayload(BaseModel):
    """Payload for bulk delete endpoint."""

    request_ids: list[int]
    delete_files: bool = True


class HealthResponse(BaseModel):
    """Health check response."""

    status: str
    version: str
    database: str
    plugins_loaded: list[str]
    shoko_signalr: Optional[str] = None  # "connected", "disconnected", "disabled"


# ============================================
# Webhook Payload Schemas (service-specific)
# ============================================


class JellyseerrWebhook(BaseModel):
    """Jellyseerr webhook payload."""

    notification_type: str
    subject: str
    message: Optional[str] = None
    media: Optional[dict] = None
    request: Optional[dict] = None
    extra: Optional[list] = None


class SonarrWebhook(BaseModel):
    """Sonarr webhook payload - flexible to accept various event types."""

    eventType: str
    series: Optional[dict] = None
    episodes: Optional[list] = None
    release: Optional[dict] = None
    episodeFile: Optional[dict] = None
    downloadId: Optional[str] = None
    downloadClient: Optional[str] = None
    isUpgrade: Optional[bool] = None

    class Config:
        extra = "allow"


class RadarrWebhook(BaseModel):
    """Radarr webhook payload - flexible to accept various event types."""

    eventType: str
    movie: Optional[dict] = None
    release: Optional[dict] = None
    movieFile: Optional[dict] = None
    downloadId: Optional[str] = None
    downloadClient: Optional[str] = None
    isUpgrade: Optional[bool] = None

    class Config:
        extra = "allow"


class QbitWebhook(BaseModel):
    """qBittorrent 'run on complete' webhook payload."""

    hash: str
    name: str
    path: Optional[str] = None


# ============================================
# SSE Event Schemas
# ============================================


class SSEUpdate(BaseModel):
    """Server-sent event payload for real-time updates."""

    event_type: str  # "state_change", "progress_update", "new_request"
    request_id: int
    request: MediaRequestResponse


# ============================================
# Library Sync Schemas
# ============================================


class SyncResultResponse(BaseModel):
    """Result of a library sync operation."""

    total_scanned: int
    added: int
    updated: int = 0  # Existing entries with missing metadata filled in
    skipped: int
    errors: int
    error_details: list[str] = []
