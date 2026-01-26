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

    async def lookup_movie(self, tmdb_id: int) -> Optional[dict]:
        """
        Lookup movie from TMDB via Radarr (gets full metadata including alternate titles).

        Args:
            tmdb_id: TMDB movie ID

        Returns:
            Full movie metadata including alternateTitles
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/api/v3/movie/lookup/tmdb", params={"tmdbId": tmdb_id})

            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"Movie lookup failed for TMDB {tmdb_id}: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error looking up movie: {e}")
            return None

    async def update_movie(self, movie: dict) -> bool:
        """
        Update a movie in Radarr (e.g., to add alternate titles).

        Args:
            movie: Full movie object with updates

        Returns:
            True if successful
        """
        try:
            client = await self._get_client()
            movie_id = movie.get("id")
            response = await client.put(f"/api/v3/movie/{movie_id}", json=movie)

            if response.status_code == 200:
                logger.info(f"Successfully updated Radarr movie {movie_id}")
                return True
            else:
                error_text = response.text[:200] if response.text else "No error body"
                logger.error(
                    f"Failed to update movie {movie_id}: status={response.status_code}, "
                    f"error={error_text}"
                )
                return False

        except Exception as e:
            logger.error(f"Error updating movie: {e}")
            return False

    async def add_alternate_titles(self, movie_id: int, titles: list[str]) -> bool:
        """
        Add alternate titles to a movie for better release matching.

        Used for anime where Japanese titles differ from English titles.

        Args:
            movie_id: Radarr movie ID
            titles: List of alternate title strings to add

        Returns:
            True if successful
        """
        try:
            # Get current movie data
            movie = await self.get_movie(movie_id)
            if not movie:
                logger.error(f"Movie {movie_id} not found in Radarr")
                return False

            # Get existing alternate titles
            existing_titles = movie.get("alternateTitles", [])
            existing_title_strings = {t.get("title", "").lower() for t in existing_titles}

            logger.info(
                f"Movie {movie_id} has {len(existing_titles)} existing alternate titles: "
                f"{[t.get('title', '') for t in existing_titles[:5]]}"
            )

            # Add new titles that don't already exist
            new_titles_added = []
            for title in titles:
                if title.lower() not in existing_title_strings:
                    existing_titles.append({
                        "sourceType": "user",
                        "movieMetadataId": movie.get("movieMetadataId", 0),
                        "title": title,
                        "cleanTitle": title.lower().replace(" ", ""),
                    })
                    new_titles_added.append(title)

            if not new_titles_added:
                logger.info(f"All alternate titles already exist for movie {movie_id}")
                return True

            # Update movie with new alternate titles
            movie["alternateTitles"] = existing_titles
            if await self.update_movie(movie):
                logger.info(f"Added NEW alternate titles to movie {movie_id}: {new_titles_added}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error adding alternate titles: {e}")
            return False

    async def sync_alternate_titles_from_tmdb(self, movie_id: int) -> bool:
        """
        Sync alternate titles from TMDB metadata for a movie.

        Fetches alternate titles from TMDB via Radarr lookup and adds any missing ones.
        Useful for anime where Japanese titles are needed for release matching.

        Args:
            movie_id: Radarr movie ID

        Returns:
            True if successful
        """
        try:
            # Get current movie
            movie = await self.get_movie(movie_id)
            if not movie:
                return False

            tmdb_id = movie.get("tmdbId")
            if not tmdb_id:
                logger.warning(f"Movie {movie_id} has no TMDB ID")
                return False

            # Lookup full metadata from TMDB via Radarr
            lookup_data = await self.lookup_movie(tmdb_id)
            if not lookup_data:
                return False

            # Get alternate titles from lookup
            lookup_titles = lookup_data.get("alternateTitles", [])
            if not lookup_titles:
                logger.debug(f"No alternate titles found in TMDB lookup for movie {movie_id}")
                return True

            # Extract title strings
            title_strings = [t.get("title") for t in lookup_titles if t.get("title")]

            # Add them to the movie
            return await self.add_alternate_titles(movie_id, title_strings)

        except Exception as e:
            logger.error(f"Error syncing alternate titles: {e}")
            return False

    async def trigger_search(self, movie_id: int) -> bool:
        """
        Trigger an automatic search for a movie.

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
                    "name": "MoviesSearch",
                    "movieIds": [movie_id]
                }
            )
            if response.status_code in (200, 201):
                logger.info(f"Triggered search for Radarr movie {movie_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error triggering Radarr search: {e}")
            return False

    async def refresh_movie(self, movie_id: int) -> bool:
        """
        Refresh metadata for a movie.

        This can help Radarr re-index alternate titles.

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
                    "name": "RefreshMovie",
                    "movieIds": [movie_id]
                }
            )
            if response.status_code in (200, 201):
                logger.info(f"Triggered refresh for Radarr movie {movie_id}")
                return True
            return False

        except Exception as e:
            logger.error(f"Error triggering Radarr refresh: {e}")
            return False

    async def search_releases(self, movie_id: int) -> list[dict]:
        """
        Get available releases for a movie from indexers.

        Args:
            movie_id: Radarr movie ID

        Returns:
            List of release dictionaries with download info
        """
        try:
            client = await self._get_client()
            response = await client.get(
                "/api/v3/release",
                params={"movieId": movie_id}
            )

            if response.status_code == 200:
                releases = response.json()
                approved_count = len([r for r in releases if r.get("approved", False)])
                rejected_count = len(releases) - approved_count
                logger.info(
                    f"Found {len(releases)} releases for movie {movie_id} "
                    f"({approved_count} approved, {rejected_count} rejected)"
                )

                # Log rejection reasons for first few rejected releases
                rejected = [r for r in releases if not r.get("approved", False)][:3]
                for r in rejected:
                    reasons = r.get("rejections", [])
                    title = r.get("title", "Unknown")[:50]
                    if reasons:
                        logger.debug(f"Rejected '{title}...': {reasons[:3]}")

                return releases
            return []

        except Exception as e:
            logger.error(f"Error searching releases: {e}")
            return []

    async def grab_release(self, guid: str, indexer_id: int) -> bool:
        """
        Grab (download) a specific release.

        Args:
            guid: Release GUID from search results
            indexer_id: Indexer ID from search results

        Returns:
            True if grab was successful
        """
        try:
            client = await self._get_client()
            response = await client.post(
                "/api/v3/release",
                json={
                    "guid": guid,
                    "indexerId": indexer_id
                }
            )

            if response.status_code in (200, 201):
                logger.info(f"Grabbed release {guid[:20]}...")
                return True
            else:
                logger.warning(f"Failed to grab release: {response.status_code}")
                return False

        except Exception as e:
            logger.error(f"Error grabbing release: {e}")
            return False

    async def search_and_grab_anime(self, movie_id: int, alternate_titles: list[str]) -> bool:
        """
        Search for anime releases using alternate titles and grab the best match.

        For anime, indexers often have releases with Japanese titles that don't
        match the English title Radarr uses for searching. This method:
        1. Searches using the standard Radarr search
        2. If releases found but none approved, logs rejection reasons
        3. If approved releases found, grabs the best one

        Note: This is a best-effort approach. True alternate title searching
        requires Prowlarr/indexer configuration.

        Args:
            movie_id: Radarr movie ID
            alternate_titles: List of alternate titles to try

        Returns:
            True if a release was grabbed
        """
        # First try the standard search
        releases = await self.search_releases(movie_id)

        if not releases:
            logger.info(f"No releases found for movie {movie_id}")
            return False

        # Filter to approved releases (passed quality/custom format checks)
        approved = [r for r in releases if r.get("approved", False)]

        if approved:
            # Sort by quality score descending
            approved.sort(key=lambda r: r.get("qualityWeight", 0), reverse=True)
            best = approved[0]

            guid = best.get("guid")
            indexer_id = best.get("indexerId")

            if guid and indexer_id:
                release_title = best.get("title", "Unknown")
                logger.info(f"Grabbing release for movie {movie_id}: {release_title[:60]}...")
                return await self.grab_release(guid, indexer_id)

        # Log common rejection reasons to help diagnose issues
        rejected = [r for r in releases if not r.get("approved", False)]
        if rejected:
            # Collect all unique rejection reasons
            all_reasons = set()
            for r in rejected:
                reasons = r.get("rejections", [])
                all_reasons.update(reasons)

            common_reasons = list(all_reasons)[:5]
            logger.warning(
                f"Found {len(releases)} releases but none approved for movie {movie_id}. "
                f"Common rejections: {common_reasons}"
            )

        return False


# Singleton instance
radarr_client = RadarrClient()
