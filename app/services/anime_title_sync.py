"""Service for syncing anime alternate titles to enable release grabbing.

For anime, releases often use Japanese titles that differ from English titles
in Radarr/Sonarr. This service:
1. Detects anime movies/shows
2. Fetches alternate titles from TMDB via Radarr/Sonarr
3. Adds them to the arr application for better release matching
4. Triggers a search to find releases
5. Stores titles in our database for Shoko matching

The service handles the async nature of media being added to Radarr:
- Jellyseerr webhook fires before Radarr has the movie
- We poll Radarr until the movie appears
- Then sync titles and trigger search
"""

import asyncio
import json
import logging
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.clients.radarr import radarr_client
from app.models import MediaRequest

logger = logging.getLogger(__name__)

# Configuration
RADARR_POLL_INTERVAL = 2  # seconds between Radarr checks
RADARR_POLL_TIMEOUT = 30  # max seconds to wait for movie in Radarr


class AnimeTitleSyncService:
    """
    Service for syncing anime alternate titles to Radarr.

    Designed to run as a background task after request creation.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_movie_titles(
        self,
        request_id: int,
        tmdb_id: int,
    ) -> bool:
        """
        Sync alternate titles for an anime movie.

        This method:
        1. Waits for Radarr to have the movie (polled from Jellyseerr)
        2. Checks if it's anime (by genres)
        3. Fetches alternate titles from TMDB
        4. Adds them to Radarr
        5. Stores them in our database
        6. Triggers a search

        Args:
            request_id: Our MediaRequest ID
            tmdb_id: TMDB movie ID

        Returns:
            True if sync was successful or not needed (non-anime)
        """
        logger.info(f"Starting anime title sync for TMDB {tmdb_id}")

        # Wait for movie to appear in Radarr
        movie = await self._wait_for_radarr_movie(tmdb_id)
        if not movie:
            logger.warning(f"Movie TMDB {tmdb_id} not found in Radarr after timeout")
            return False

        radarr_id = movie.get("id")
        title = movie.get("title", "Unknown")

        # Check if it's anime
        if not self._is_anime(movie):
            logger.debug(f"Movie '{title}' is not anime, skipping title sync")
            return True

        logger.info(f"Detected anime movie: '{title}' (Radarr ID: {radarr_id})")

        # Fetch alternate titles from TMDB
        alternate_titles = await self._fetch_alternate_titles(tmdb_id)
        if not alternate_titles:
            logger.debug(f"No alternate titles found for '{title}'")
            return True

        logger.info(f"Found {len(alternate_titles)} alternate titles for '{title}'")

        # Add to Radarr
        success = await radarr_client.add_alternate_titles(radarr_id, alternate_titles)
        if not success:
            logger.error(f"Failed to add alternate titles to Radarr for '{title}'")
            return False

        # Store in our database
        await self._store_titles(request_id, radarr_id, alternate_titles)

        # Try to search and grab automatically
        grabbed = await radarr_client.search_and_grab_anime(radarr_id, alternate_titles)
        if grabbed:
            logger.info(f"Successfully grabbed release for '{title}'")
        else:
            # Fallback to standard search (Radarr will grab on its own schedule)
            await radarr_client.trigger_search(radarr_id)
            logger.info(f"No approved releases - triggered search for '{title}'")

        return True

    async def _wait_for_radarr_movie(self, tmdb_id: int) -> Optional[dict]:
        """
        Poll Radarr until the movie appears.

        Jellyseerr sends webhook before Radarr has the movie,
        so we need to wait for Radarr to process the request.
        """
        elapsed = 0
        while elapsed < RADARR_POLL_TIMEOUT:
            movie = await radarr_client.get_movie_by_tmdb(tmdb_id)
            if movie:
                return movie

            await asyncio.sleep(RADARR_POLL_INTERVAL)
            elapsed += RADARR_POLL_INTERVAL

        return None

    def _is_anime(self, movie: dict) -> bool:
        """
        Check if a movie is anime based on genres and tags.
        """
        genres = movie.get("genres", [])
        tags = movie.get("tags", [])

        # Check genres (from TMDB)
        genre_names = [g.lower() for g in genres]
        if "animation" in genre_names or "anime" in genre_names:
            return True

        # Check tags (from Radarr custom tags)
        tag_names = [str(t).lower() for t in tags]
        if "anime" in tag_names:
            return True

        # Check path (if stored in anime folder)
        path = movie.get("path", "").lower()
        if "/anime/" in path:
            return True

        return False

    async def _fetch_alternate_titles(self, tmdb_id: int) -> list[str]:
        """
        Fetch alternate titles from TMDB via Radarr lookup.
        """
        lookup_data = await radarr_client.lookup_movie(tmdb_id)
        if not lookup_data:
            return []

        lookup_titles = lookup_data.get("alternateTitles", [])
        return [t.get("title") for t in lookup_titles if t.get("title")]

    async def _store_titles(
        self,
        request_id: int,
        radarr_id: int,
        titles: list[str],
    ) -> None:
        """
        Store alternate titles in our database.
        """
        stmt = select(MediaRequest).where(MediaRequest.id == request_id)
        result = await self.db.execute(stmt)
        request = result.scalar_one_or_none()

        if request:
            request.alternate_titles = json.dumps(titles)
            request.is_anime = True
            request.radarr_id = radarr_id
            await self.db.commit()
            logger.debug(f"Stored {len(titles)} alternate titles for request {request_id}")


async def sync_anime_titles_background(
    db_factory,
    request_id: int,
    tmdb_id: int,
) -> None:
    """
    Background task wrapper for anime title sync.

    Creates its own database session to avoid issues with
    the original session being closed.

    Args:
        db_factory: Async session factory (async_session_maker)
        request_id: Our MediaRequest ID
        tmdb_id: TMDB movie ID
    """
    try:
        async with db_factory() as db:
            service = AnimeTitleSyncService(db)
            await service.sync_movie_titles(request_id, tmdb_id)
    except Exception as e:
        logger.error(f"Error in background anime title sync: {e}")
