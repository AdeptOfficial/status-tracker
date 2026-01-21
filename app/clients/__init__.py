"""API clients for external services."""

from app.clients.qbittorrent import QBittorrentClient
from app.clients.shoko import ShokoClient
from app.clients.jellyfin import JellyfinClient, jellyfin_client
from app.clients.sonarr import SonarrClient, sonarr_client
from app.clients.radarr import RadarrClient, radarr_client
from app.clients.jellyseerr import JellyseerrClient, jellyseerr_client

__all__ = [
    "QBittorrentClient",
    "ShokoClient",
    "JellyfinClient",
    "jellyfin_client",
    "SonarrClient",
    "sonarr_client",
    "RadarrClient",
    "radarr_client",
    "JellyseerrClient",
    "jellyseerr_client",
]
