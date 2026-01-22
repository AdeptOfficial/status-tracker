"""Mock qBittorrent client for testing."""

from typing import Optional


class MockQBittorrentClient:
    """
    Mock qBittorrent client for testing download progress.

    Usage:
        mock_qbit = MockQBittorrentClient()
        mock_qbit.add_torrent("ABC123", progress=0.5)
        torrents = await mock_qbit.get_torrents()
    """

    def __init__(self):
        self.torrents: dict[str, dict] = {}

    def add_torrent(
        self,
        hash: str,
        progress: float = 0.0,
        state: str = "downloading",
        name: str = "Test Torrent",
        size: int = 1000000000,
        dlspeed: int = 1000000,
        eta: int = 3600,
    ):
        """Add a mock torrent."""
        self.torrents[hash.upper()] = {
            "hash": hash.upper(),
            "name": name,
            "progress": progress,
            "state": state,
            "size": size,
            "dlspeed": dlspeed,
            "eta": eta,
            "completed": int(size * progress),
        }

    def set_progress(self, hash: str, progress: float):
        """Update torrent progress."""
        hash_upper = hash.upper()
        if hash_upper in self.torrents:
            self.torrents[hash_upper]["progress"] = progress
            if progress >= 1.0:
                self.torrents[hash_upper]["state"] = "completed"

    def remove_torrent(self, hash: str):
        """Remove a mock torrent."""
        self.torrents.pop(hash.upper(), None)

    async def get_torrents(self) -> list[dict]:
        """Return all mock torrents."""
        return list(self.torrents.values())

    async def get_torrent(self, hash: str) -> Optional[dict]:
        """Return a specific torrent by hash."""
        return self.torrents.get(hash.upper())
