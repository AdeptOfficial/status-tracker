"""Sonarr API v3 client for deletion operations."""

import logging
from typing import Optional

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


class SonarrClient:
    """
    Async client for Sonarr API v3.

    Used for:
    - Deleting series (with or without files)
    - Verifying deletion
    - Getting series info
    """

    def __init__(self):
        self.base_url = settings.sonarr_base_url
        self.api_key = settings.SONARR_API_KEY
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

    async def delete_series(self, series_id: int, delete_files: bool = True) -> tuple[bool, str]:
        """
        Delete a series from Sonarr.

        Args:
            series_id: Sonarr series ID
            delete_files: If True, delete files from disk

        Returns:
            Tuple of (success, message)
        """
        try:
            client = await self._get_client()
            response = await client.delete(
                f"/api/v3/series/{series_id}",
                params={"deleteFiles": str(delete_files).lower()}
            )

            if response.status_code == 200:
                logger.info(f"Successfully deleted Sonarr series {series_id} (deleteFiles={delete_files})")
                return True, "Series deleted successfully"
            elif response.status_code == 404:
                logger.info(f"Sonarr series {series_id} not found (already deleted?)")
                return True, "Series not found (already deleted)"
            else:
                error_msg = f"Delete failed with status {response.status_code}"
                try:
                    error_data = response.json()
                    if "message" in error_data:
                        error_msg = error_data["message"]
                except Exception:
                    pass
                logger.error(f"Failed to delete Sonarr series {series_id}: {error_msg}")
                return False, error_msg

        except httpx.RequestError as e:
            error_msg = f"Request error: {e}"
            logger.error(f"Request error deleting Sonarr series: {e}")
            return False, error_msg
        except Exception as e:
            error_msg = f"Unexpected error: {e}"
            logger.error(f"Unexpected error deleting Sonarr series: {e}")
            return False, error_msg

    async def get_series(self, series_id: int) -> Optional[dict]:
        """
        Get series by ID (for verification).

        Args:
            series_id: Sonarr series ID

        Returns:
            Series data dict if found, None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/api/v3/series/{series_id}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.warning(f"Unexpected status getting series {series_id}: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting Sonarr series: {e}")
            return None

    async def get_series_by_tvdb(self, tvdb_id: int) -> Optional[dict]:
        """
        Lookup series by TVDB ID.

        Args:
            tvdb_id: TVDB ID

        Returns:
            Series data dict if found, None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/v3/series", params={"tvdbId": tvdb_id})

            if response.status_code == 200:
                series_list = response.json()
                if series_list:
                    return series_list[0]
            return None

        except Exception as e:
            logger.error(f"Error looking up Sonarr series by TVDB: {e}")
            return None

    async def trigger_rescan(self, series_id: int) -> bool:
        """
        Trigger a rescan of series files.

        Args:
            series_id: Sonarr series ID

        Returns:
            True if command sent successfully
        """
        try:
            client = await self._get_client()
            response = await client.post(
                "/api/v3/command",
                json={
                    "name": "RescanSeries",
                    "seriesId": series_id
                }
            )
            return response.status_code in (200, 201)

        except Exception as e:
            logger.error(f"Error triggering Sonarr rescan: {e}")
            return False

    async def health_check(self) -> bool:
        """Check if Sonarr is reachable."""
        try:
            client = await self._get_client()
            response = await client.get("/api/v3/system/status")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Sonarr health check failed: {e}")
            return False

    async def get_episode_count(self, series_id: int, season_number: int) -> Optional[int]:
        """
        Get total episode count for a specific series/season.

        This is used to get the actual episode count for GRABBING state display,
        since per-episode grabs send individual webhooks (each with episodes=[1 episode])
        and we need the true total, not just len(webhook.episodes).

        Args:
            series_id: Sonarr series ID
            season_number: Season number to count episodes for

        Returns:
            Episode count if found, None on error
        """
        try:
            client = await self._get_client()
            response = await client.get(
                "/api/v3/episode",
                params={"seriesId": series_id, "seasonNumber": season_number}
            )

            if response.status_code == 200:
                episodes = response.json()
                count = len(episodes)
                logger.debug(f"Sonarr: series {series_id} season {season_number} has {count} episodes")
                return count
            else:
                logger.warning(f"Failed to get episodes for series {series_id}: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting Sonarr episode count: {e}")
            return None

    async def get_all_series(self) -> list[dict]:
        """
        Fetch all series from Sonarr for bulk sync.

        Returns:
            List of series with id, tvdbId, title, path, etc.
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/v3/series")

            if response.status_code == 200:
                series = response.json()
                logger.info(f"Fetched {len(series)} series from Sonarr")
                return series
            else:
                logger.error(f"Failed to fetch Sonarr series: {response.status_code}")
                return []

        except httpx.RequestError as e:
            logger.error(f"Request error fetching Sonarr series: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Sonarr series: {e}")
            return []


    async def lookup_series(self, tvdb_id: int) -> Optional[dict]:
        """
        Lookup series from TVDB via Sonarr (gets full metadata including alternate titles).

        Args:
            tvdb_id: TVDB series ID

        Returns:
            Full series metadata including alternateTitles
        """
        try:
            client = await self._get_client()
            response = await client.get("/api/v3/series/lookup", params={"term": f"tvdb:{tvdb_id}"})

            if response.status_code == 200:
                results = response.json()
                return results[0] if results else None
            else:
                logger.warning(f"Series lookup failed for TVDB {tvdb_id}: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error looking up series: {e}")
            return None

    async def add_alternate_titles(self, series_id: int, titles: list[str]) -> bool:
        """
        Add alternate titles to a series for better release matching.

        Used for anime where Japanese titles differ from English titles.

        Args:
            series_id: Sonarr series ID
            titles: List of alternate title strings to add

        Returns:
            True if successful
        """
        try:
            # Get current series data
            series = await self.get_series(series_id)
            if not series:
                logger.error(f"Series {series_id} not found in Sonarr")
                return False

            # Get existing alternate titles
            existing_titles = series.get("alternateTitles", [])
            existing_title_strings = {t.get("title", "").lower() for t in existing_titles}

            logger.info(
                f"Series {series_id} has {len(existing_titles)} existing alternate titles: "
                f"{[t.get('title', '') for t in existing_titles[:5]]}"
            )

            # Add new titles that don't already exist
            new_titles_added = []
            for title in titles:
                if title.lower() not in existing_title_strings:
                    existing_titles.append({
                        "title": title,
                        "seasonNumber": -1,  # -1 means all seasons
                    })
                    new_titles_added.append(title)

            if not new_titles_added:
                logger.info(f"All alternate titles already exist for series {series_id}")
                return True

            # Update series with new alternate titles
            series["alternateTitles"] = existing_titles
            success = await self.update_series(series)

            if success:
                logger.info(
                    f"Added {len(new_titles_added)} alternate titles to series {series_id}: "
                    f"{new_titles_added[:3]}"
                )
            return success

        except Exception as e:
            logger.error(f"Error adding alternate titles to series: {e}")
            return False

    async def update_series(self, series: dict) -> bool:
        """
        Update a series in Sonarr (e.g., to add alternate titles).

        Args:
            series: Full series object with updates

        Returns:
            True if successful
        """
        try:
            client = await self._get_client()
            series_id = series.get("id")
            response = await client.put(f"/api/v3/series/{series_id}", json=series)

            if response.status_code == 200:
                logger.info(f"Successfully updated Sonarr series {series_id}")
                return True
            else:
                error_text = response.text[:200] if response.text else "No error body"
                logger.error(
                    f"Failed to update series {series_id}: status={response.status_code}, "
                    f"error={error_text}"
                )
                return False

        except Exception as e:
            logger.error(f"Error updating series: {e}")
            return False


# Singleton instance
sonarr_client = SonarrClient()
