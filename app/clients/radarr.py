"""Radarr API v3 client for deletion operations."""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class RadarrClient:
    """
    Async client for Radarr API v3.

    Used for:
    - Deleting movies (with or without files)
    - Verifying deletion
    - Getting movie info
    """

    def __init__(self):
        self.base_url = settings.radarr_base_url
        self.api_key = settings.RADARR_API_KEY
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=60.0,  # Longer timeout for delete operations
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

    async def delete_movie(self, movie_id: int, delete_files: bool = True) -> tuple[bool, str]:
        """
        Delete a movie from Radarr.

        Args:
            movie_id: Radarr movie ID
            delete_files: If True, delete files from disk

        Returns:
            Tuple of (success, message)
        """
        try:
            client = await self._get_client()
            response = await client.delete(
                f"/api/v3/movie/{movie_id}",
                params={"deleteFiles": str(delete_files).lower()}
            )

            if response.status_code == 200:
                logger.info(f"Successfully deleted Radarr movie {movie_id} (deleteFiles={delete_files})")
                return True, "Movie deleted successfully"
            elif response.status_code == 404:
                logger.info(f"Radarr movie {movie_id} not found (already deleted?)")
                return True, "Movie not found (already deleted)"
            else:
                error_msg = f"Delete failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg = error_data["message"]
                except Exception as json_err:
                    # Log response body for debugging if JSON parse fails
                    logger.warning(f"Could not parse Radarr error response: {response.text[:200]}")
                logger.error(f"Failed to delete Radarr movie {movie_id}: {error_msg}")
                return False, error_msg

        except httpx.RequestError as e:
            error_msg = f"Request error: {e}"
            logger.error(f"Request error deleting Radarr movie: {e}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Unexpected error deleting Radarr movie: {e}")
            return False, error_msg

    async def get_movie(self, movie_id: int) -> Optional[dict]:
        """
        Get movie by ID (for verification).

        Args:
            movie_id: Radarr movie ID

        Returns:
            Movie data dict if found, None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/api/v3/movie/{movie_id}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.warning(f"Unexpected status getting movie {movie_id}: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting Radarr movie: {e}")
            return None

    async def get_movie_by_tmdb(self, tmdb_id: int) -> Optional[dict]:
        """
        Lookup movie by TMDB ID.

        Args:
            tmdb_id: TMDB ID

        Returns:
            Movie data dict if found, None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/v3/movie", params={"tmdbId": tmdb_id})

            if response.status_code == 200:
                movies = response.json()
                if movies:
                    return movies[0]
            return None

        except Exception as e:
            logger.error(f"Error looking up Radarr movie by TMDB: {e}")
            return None

    async def trigger_rescan(self, movie_id: int) -> bool:
        """
        Trigger a rescan of movie files.

        Args:
            movie_id: Radarr movie ID

        Returns:
            True if command sent successfully
        """
        try:
            client = await self._get_client()
            response = await client.post(
                "/api/v3/command",
                json={
                    "name": "RescanMovie",
                    "movieId": movie_id
                }
            )
            return response.status_code in (200, 201)

        except Exception as e:
            logger.error(f"Error triggering Radarr rescan: {e}")
            return False

    async def health_check(self) -> bool:
        """Check if Radarr is reachable."""
        try:
            client = await self._get_client()
            response = await client.get("/api/v3/system/status")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Radarr health check failed: {e}")
            return False

    async def get_all_movies(self) -> list[dict]:
        """
        Fetch all movies from Radarr for bulk sync.

        Returns:
            List of movies with id, tmdbId, title, path, hasFile, etc.
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/v3/movie")

            if response.status_code == 200:
                movies = response.json()
                logger.info(f"Fetched {len(movies)} movies from Radarr")
                return movies
            else:
                logger.error(f"Failed to fetch Radarr movies: {response.status_code}")
                return []

        except httpx.RequestError as e:
            logger.error(f"Request error fetching Radarr movies: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Radarr movies: {e}")
            return []


# Singleton instance
radarr_client = RadarrClient()
