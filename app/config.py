"""Application configuration from environment variables."""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """
    All settings via environment variables.
    Same image for dev/prod, just change env vars.
    """

    # Logging
    LOG_LEVEL: str = "INFO"  # DEBUG, INFO, WARNING, ERROR

    # Database
    DATABASE_URL: str = "sqlite:///config/tracker.db"

    # qBittorrent (accessed via Gluetun in Docker)
    QBIT_HOST: str = "gluetun"
    QBIT_PORT: int = 8080
    QBIT_USERNAME: str = "admin"
    QBIT_PASSWORD: str = ""

    # Jellyfin external URL (for deep links users click)
    JELLYFIN_URL: str = "http://localhost:8096"

    # Shoko SignalR settings
    SHOKO_HOST: str = "shoko"
    SHOKO_PORT: int = 8111
    SHOKO_API_KEY: str = ""
    # Reconnection intervals in seconds (comma-separated)
    SHOKO_RECONNECT_INTERVALS: str = "0,2,10,30,60,120,300"

    # Polling interval for download progress
    POLL_INTERVAL: int = 5

    # Media path prefix (for matching Shoko relative paths to Sonarr/Radarr final paths)
    # Shoko reports: anime/shows/Title/Season 1/file.mkv
    # Sonarr stores: /data/anime/shows/Title/Season 1/file.mkv
    MEDIA_PATH_PREFIX: str = "/data"

    # Feature flags (for optional plugins)
    ENABLE_SHOKO: bool = True
    ENABLE_TIMEOUT_CHECKER: bool = True
    ENABLE_DELETION_SYNC: bool = False  # Enable after testing

    # Timeout settings (in minutes)
    DOWNLOADING_TIMEOUT: int = 1440  # 24 hours
    IMPORTING_TIMEOUT: int = 60  # 1 hour

    # Jellyfin API (for deletion and user validation)
    JELLYFIN_HOST: str = "jellyfin"
    JELLYFIN_PORT: int = 8096
    JELLYFIN_API_KEY: str = ""

    # Sonarr API (for TV series deletion)
    SONARR_HOST: str = "sonarr"
    SONARR_PORT: int = 8989
    SONARR_API_KEY: str = ""

    # Radarr API (for movie deletion)
    RADARR_HOST: str = "radarr"
    RADARR_PORT: int = 7878
    RADARR_API_KEY: str = ""

    # Jellyseerr API (for clearing requests after deletion)
    JELLYSEERR_HOST: str = "jellyseerr"
    JELLYSEERR_PORT: int = 5055
    JELLYSEERR_API_KEY: str = ""

    # Admin users (comma-separated Jellyfin user IDs)
    ADMIN_USER_IDS: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"

    @property
    def shoko_reconnect_intervals_list(self) -> list[int]:
        """Parse comma-separated reconnect intervals into list of ints."""
        return [int(x.strip()) for x in self.SHOKO_RECONNECT_INTERVALS.split(",")]

    @property
    def admin_user_ids_list(self) -> list[str]:
        """Parse comma-separated admin user IDs into list."""
        if not self.ADMIN_USER_IDS:
            return []
        return [x.strip() for x in self.ADMIN_USER_IDS.split(",") if x.strip()]

    @property
    def jellyfin_base_url(self) -> str:
        """Jellyfin API base URL."""
        return f"http://{self.JELLYFIN_HOST}:{self.JELLYFIN_PORT}"

    @property
    def sonarr_base_url(self) -> str:
        """Sonarr API base URL."""
        return f"http://{self.SONARR_HOST}:{self.SONARR_PORT}"

    @property
    def radarr_base_url(self) -> str:
        """Radarr API base URL."""
        return f"http://{self.RADARR_HOST}:{self.RADARR_PORT}"

    @property
    def jellyseerr_base_url(self) -> str:
        """Jellyseerr API base URL."""
        return f"http://{self.JELLYSEERR_HOST}:{self.JELLYSEERR_PORT}"


settings = Settings()
