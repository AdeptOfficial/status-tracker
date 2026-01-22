"""qBittorrent WebUI API client.

Handles authentication and torrent info queries.

qBittorrent API docs:
https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-(qBittorrent-4.1)
"""

import logging
from dataclasses import dataclass
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class TorrentInfo:
    """Parsed torrent information from qBittorrent."""

    hash: str
    name: str
    progress: float  # 0.0 to 1.0
    state: str  # downloading, uploading, pausedDL, etc.
    size: int  # Total size in bytes
    downloaded: int  # Downloaded bytes
    download_speed: int  # Bytes per second
    eta: int  # Seconds remaining (-1 if unknown)
    save_path: str


class QBittorrentClient:
    """
    Async client for qBittorrent WebUI API.

    Usage:
        client = QBittorrentClient()
        await client.login()
        torrents = await client.get_torrents(hashes=["abc123..."])
        await client.close()

    Or as context manager:
        async with QBittorrentClient() as client:
            torrents = await client.get_torrents()
    """

    def __init__(
        self,
        host: str = settings.QBIT_HOST,
        port: int = settings.QBIT_PORT,
        username: str = settings.QBIT_USERNAME,
        password: str = settings.QBIT_PASSWORD,
    ):
        self.base_url = f"http://{host}:{port}"
        self.username = username
        self.password = password
        self._client: Optional[httpx.AsyncClient] = None
        self._authenticated = False

    async def __aenter__(self):
        await self.login()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                # qBittorrent uses cookies for session auth
                cookies={},
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
            self._authenticated = False

    async def login(self) -> bool:
        """
        Authenticate with qBittorrent.

        Returns True if login successful, False otherwise.
        Session cookie is stored in the client for subsequent requests.
        """
        try:
            client = await self._get_client()

            response = await client.post(
                "/api/v2/auth/login",
                data={
                    "username": self.username,
                    "password": self.password,
                },
            )

            if response.status_code == 200 and response.text == "Ok.":
                self._authenticated = True
                logger.debug("qBittorrent login successful")
                return True

            logger.warning(
                f"qBittorrent login failed: {response.status_code} - {response.text}"
            )
            return False

        except httpx.RequestError as e:
            logger.error(f"qBittorrent connection error: {e}")
            return False

    async def get_torrents(
        self, hashes: Optional[list[str]] = None
    ) -> list[TorrentInfo]:
        """
        Get torrent information.

        Args:
            hashes: Optional list of torrent hashes to filter by.
                   If None, returns all torrents.

        Returns:
            List of TorrentInfo objects.
        """
        if not self._authenticated:
            if not await self.login():
                return []

        try:
            client = await self._get_client()

            params = {}
            if hashes:
                # qBittorrent expects pipe-separated hashes
                params["hashes"] = "|".join(hashes)

            response = await client.get("/api/v2/torrents/info", params=params)

            if response.status_code != 200:
                logger.error(f"Failed to get torrents: {response.status_code}")
                return []

            torrents = response.json()
            return [self._parse_torrent(t) for t in torrents]

        except httpx.RequestError as e:
            logger.error(f"Error getting torrents: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error parsing torrents: {e}")
            return []

    def _parse_torrent(self, data: dict) -> TorrentInfo:
        """Parse raw qBittorrent API response into TorrentInfo."""
        return TorrentInfo(
            hash=data.get("hash", ""),
            name=data.get("name", ""),
            progress=data.get("progress", 0.0),
            state=data.get("state", "unknown"),
            size=data.get("size", 0),
            downloaded=data.get("downloaded", 0),
            download_speed=data.get("dlspeed", 0),
            eta=data.get("eta", -1),
            save_path=data.get("save_path", ""),
        )

    async def get_torrent(self, hash: str) -> Optional[TorrentInfo]:
        """Get info for a single torrent by hash."""
        torrents = await self.get_torrents(hashes=[hash])
        return torrents[0] if torrents else None

    async def delete_torrent(
        self,
        hash: str,
        delete_files: bool = True,
    ) -> tuple[bool, str]:
        """
        Delete a torrent from qBittorrent.

        Args:
            hash: Torrent hash to delete
            delete_files: If True, also delete downloaded files from disk

        Returns:
            Tuple of (success, message)
        """
        if not self._authenticated:
            if not await self.login():
                return False, "Failed to authenticate with qBittorrent"

        try:
            client = await self._get_client()

            # First check if torrent exists
            existing = await self.get_torrent(hash)
            if not existing:
                logger.info(f"Torrent {hash[:8]}... not found in qBittorrent (already removed?)")
                return True, "Torrent not found (already removed)"

            # Delete the torrent
            response = await client.post(
                "/api/v2/torrents/delete",
                data={
                    "hashes": hash,
                    "deleteFiles": "true" if delete_files else "false",
                },
            )

            if response.status_code == 200:
                logger.info(
                    f"Deleted torrent {hash[:8]}... from qBittorrent "
                    f"(deleteFiles={delete_files})"
                )
                return True, f"Torrent deleted successfully (files {'deleted' if delete_files else 'kept'})"
            else:
                error_msg = f"Delete failed with status {response.status_code}"
                logger.error(f"Failed to delete torrent {hash[:8]}...: {error_msg}")
                return False, error_msg

        except httpx.RequestError as e:
            error_msg = f"Request error: {e}"
            logger.error(f"Request error deleting torrent: {e}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Unexpected error deleting torrent: {e}")
            return False, error_msg

    async def is_healthy(self) -> bool:
        """Check if qBittorrent is reachable and authenticated."""
        try:
            if not self._authenticated:
                return await self.login()

            client = await self._get_client()
            response = await client.get("/api/v2/app/version")
            return response.status_code == 200

        except Exception:
            return False


def format_speed(bytes_per_second: int) -> str:
    """Format download speed for display."""
    if bytes_per_second < 1024:
        return f"{bytes_per_second} B/s"
    elif bytes_per_second < 1024 * 1024:
        return f"{bytes_per_second / 1024:.1f} KB/s"
    elif bytes_per_second < 1024 * 1024 * 1024:
        return f"{bytes_per_second / (1024 * 1024):.1f} MB/s"
    else:
        return f"{bytes_per_second / (1024 * 1024 * 1024):.2f} GB/s"


def format_eta(seconds: int) -> str:
    """Format ETA for display."""
    if seconds < 0 or seconds == 8640000:  # qBit uses 8640000 for "unknown"
        return "Unknown"
    if seconds < 60:
        return f"{seconds}s"
    elif seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    elif seconds < 86400:
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        return f"{hours}h {minutes}m"
    else:
        days = seconds // 86400
        hours = (seconds % 86400) // 3600
        return f"{days}d {hours}h"


def format_size(bytes: int) -> str:
    """Format file size for display."""
    if bytes < 1024:
        return f"{bytes} B"
    elif bytes < 1024 * 1024:
        return f"{bytes / 1024:.1f} KB"
    elif bytes < 1024 * 1024 * 1024:
        return f"{bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{bytes / (1024 * 1024 * 1024):.2f} GB"
