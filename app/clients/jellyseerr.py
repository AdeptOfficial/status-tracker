"""Jellyseerr API client for request management."""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class JellyseerrClient:
    """
    Async client for Jellyseerr API.

    Used for:
    - Deleting/declining requests after media deletion
    - Getting request info
    """

    def __init__(self):
        self.base_url = settings.jellyseerr_base_url
        self.api_key = settings.JELLYSEERR_API_KEY
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                headers={
                    "X-Api-Key": self.api_key,
                    "Content-Type": "application/json",
                }
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def delete_request(self, request_id: int) -> tuple[bool, str]:
        """
        Delete a request from Jellyseerr.

        This removes the request record. Does NOT delete from Sonarr/Radarr.

        Args:
            request_id: Jellyseerr request ID

        Returns:
            Tuple of (success, message)
        """
        try:
            client = await self._get_client()
            response = await client.delete(f"/api/v1/request/{request_id}")

            if response.status_code == 200:
                logger.info(f"Successfully deleted Jellyseerr request {request_id}")
                return True, "Request deleted successfully"
            elif response.status_code == 204:
                logger.info(f"Successfully deleted Jellyseerr request {request_id}")
                return True, "Request deleted successfully"
            elif response.status_code == 404:
                logger.info(f"Jellyseerr request {request_id} not found (already deleted?)")
                return True, "Request not found (already deleted)"
            else:
                error_msg = f"Delete failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg = error_data["message"]
                except Exception:
                    pass
                logger.error(f"Failed to delete Jellyseerr request {request_id}: {error_msg}")
                return False, error_msg

        except httpx.RequestError as e:
            error_msg = f"Request error: {e}"
            logger.error(f"Request error deleting Jellyseerr request: {e}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Unexpected error deleting Jellyseerr request: {e}")
            return False, error_msg

    async def get_request(self, request_id: int) -> Optional[dict]:
        """
        Get request by ID (for verification).

        Args:
            request_id: Jellyseerr request ID

        Returns:
            Request data dict if found, None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/api/v1/request/{request_id}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.warning(f"Unexpected status getting request {request_id}: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting Jellyseerr request: {e}")
            return None

    async def get_request_by_tmdb(self, tmdb_id: int, media_type: str) -> Optional[dict]:
        """
        Lookup request by TMDB ID.

        Args:
            tmdb_id: TMDB ID
            media_type: "movie" or "tv"

        Returns:
            Request data dict if found, None if not found
        """
        try:
            client = await self._get_client()
            # Get media by TMDB ID first
            response = await client.get(f"/api/v1/{media_type}/{tmdb_id}")

            if response.status_code == 200:
                media_data = response.json()
                # Check if there's a pending/approved request
                if "requests" in media_data and media_data["requests"]:
                    return media_data["requests"][0]
            return None

        except Exception as e:
            logger.error(f"Error looking up Jellyseerr request by TMDB: {e}")
            return None

    async def health_check(self) -> bool:
        """Check if Jellyseerr is reachable."""
        try:
            client = await self._get_client()
            response = await client.get("/api/v1/status")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Jellyseerr health check failed: {e}")
            return False

    async def get_media_id_by_tmdb(self, tmdb_id: int, media_type: str) -> Optional[int]:
        """
        Look up Jellyseerr media entry ID by TMDB ID.

        Jellyseerr tracks "requests" (user submissions) separately from "media"
        (availability status). To clear the "Available" badge after deletion,
        we need to delete the media entry, not just the request.

        Args:
            tmdb_id: TMDB ID of the movie/show
            media_type: "movie" or "tv"

        Returns:
            mediaInfo.id if found, None otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/api/v1/{media_type}/{tmdb_id}")

            if response.status_code == 200:
                data = response.json()
                media_info = data.get("mediaInfo")
                if media_info:
                    return media_info.get("id")
            return None

        except Exception as e:
            logger.error(f"Error looking up Jellyseerr media by TMDB {tmdb_id}: {e}")
            return None

    async def delete_media(self, media_id: int) -> tuple[bool, str]:
        """
        Delete a media entry from Jellyseerr.

        This removes the media availability record, clearing the "Available"
        status from the UI. This is separate from delete_request() which only
        removes the request record.

        Note: This also removes all associated requests and can trigger
        deletion from Radarr/Sonarr if configured.

        Args:
            media_id: Jellyseerr media entry ID (from mediaInfo.id)

        Returns:
            Tuple of (success, message)
        """
        try:
            client = await self._get_client()
            response = await client.delete(f"/api/v1/media/{media_id}")

            if response.status_code in (200, 204):
                logger.info(f"Successfully deleted Jellyseerr media entry {media_id}")
                return True, "Media entry deleted - availability cleared"
            elif response.status_code == 404:
                logger.info(f"Jellyseerr media {media_id} not found (already deleted?)")
                return True, "Media not found (already deleted)"
            else:
                error_msg = f"Delete media failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg = error_data["message"]
                except Exception:
                    pass
                logger.error(f"Failed to delete Jellyseerr media {media_id}: {error_msg}")
                return False, error_msg

        except httpx.RequestError as e:
            error_msg = f"Request error: {e}"
            logger.error(f"Request error deleting Jellyseerr media: {e}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Unexpected error deleting Jellyseerr media: {e}")
            return False, error_msg


# Singleton instance
jellyseerr_client = JellyseerrClient()
