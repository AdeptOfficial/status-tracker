"""Mock clients for testing."""

from .qbittorrent import MockQBittorrentClient
from .jellyfin import MockJellyfinClient
from .shoko import MockShokoClient

__all__ = ["MockQBittorrentClient", "MockJellyfinClient", "MockShokoClient"]
