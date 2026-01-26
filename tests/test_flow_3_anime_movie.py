"""Test Flow 3: Anime Movie.

Tests the complete flow for anime movies:
APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → ANIME_MATCHING → AVAILABLE

Key differences from regular movies:
- is_anime detected from movie.tags at Grab time
- Goes through ANIME_MATCHING instead of IMPORTING
- Multi-type fallback in Jellyfin (Movie → Series → Any → Title)
- Shoko FileMatched triggers Jellyfin verification

Uses captured webhooks from docs/flows/captured-webhooks/ to test
real-world scenarios.
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from dataclasses import dataclass

from app.models import MediaRequest, MediaType, RequestState
from app.plugins.jellyseerr import JellyseerrPlugin
from app.plugins.radarr import RadarrPlugin


class TestAnimeDetection:
    """Test anime detection from movie.tags."""

    @pytest.mark.asyncio
    async def test_anime_detected_from_tags(self, db_session, load_webhook):
        """is_anime=True when movie.tags contains 'anime'."""
        # Create request (simulating Jellyseerr)
        request = MediaRequest(
            title="The Tunnel to Summer, the Exit of Goodbyes",
            media_type=MediaType.MOVIE,
            state=RequestState.APPROVED,
            tmdb_id=533514,
        )
        db_session.add(request)
        await db_session.commit()

        # Process Radarr Grab (which has anime tag)
        plugin = RadarrPlugin()
        grab_payload = load_webhook("radarr-grab")

        result = await plugin.handle_webhook(grab_payload, db_session)
        await db_session.commit()

        # The captured webhook has anime tag
        assert result.is_anime is True

    @pytest.mark.asyncio
    async def test_non_anime_detected_from_tags(self, db_session):
        """is_anime=False when movie.tags doesn't contain 'anime'."""
        request = MediaRequest(
            title="Regular Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.APPROVED,
            tmdb_id=12345,
        )
        db_session.add(request)
        await db_session.commit()

        # Mock payload without anime tag
        plugin = RadarrPlugin()
        payload = {
            "eventType": "Grab",
            "movie": {
                "id": 1,
                "title": "Regular Movie",
                "tmdbId": 12345,
                "tags": ["action", "thriller"],  # No anime tag
            },
            "release": {
                "quality": "Bluray-1080p",
                "indexer": "TorrentLeech",
            },
            "downloadId": "ABC123DEF456789012345678901234567890ABCD",
        }

        result = await plugin.handle_webhook(payload, db_session)
        await db_session.commit()

        assert result.is_anime is False


class TestAnimeMovieImport:
    """Test anime movie import routing to ANIME_MATCHING."""

    @pytest.mark.asyncio
    async def test_anime_import_goes_to_anime_matching(self, db_session, load_webhook):
        """Anime movie routes to ANIME_MATCHING state after import."""
        # Use TMDB ID from radarr-import.json webhook (1052946)
        request = MediaRequest(
            title="Violet Evergarden: Recollections",
            media_type=MediaType.MOVIE,
            state=RequestState.DOWNLOADED,
            tmdb_id=1052946,  # Must match webhook's movie.tmdbId
            is_anime=True,  # Detected at grab time
        )
        db_session.add(request)
        await db_session.commit()

        plugin = RadarrPlugin()
        import_payload = load_webhook("radarr-import")

        result = await plugin.handle_webhook(import_payload, db_session)
        await db_session.commit()

        assert result.state == RequestState.ANIME_MATCHING

    @pytest.mark.asyncio
    async def test_non_anime_import_goes_to_importing(self, db_session, load_webhook):
        """Non-anime movie routes to IMPORTING state after import."""
        # Use TMDB ID from radarr-import.json webhook
        request = MediaRequest(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.DOWNLOADED,
            tmdb_id=1052946,  # Must match webhook's movie.tmdbId
            is_anime=False,  # Not anime
        )
        db_session.add(request)
        await db_session.commit()

        plugin = RadarrPlugin()
        import_payload = load_webhook("radarr-import")

        result = await plugin.handle_webhook(import_payload, db_session)
        await db_session.commit()

        assert result.state == RequestState.IMPORTING


class TestMultiTypeFallback:
    """Test multi-type fallback verification for anime movies."""

    @pytest.mark.asyncio
    async def test_found_as_movie(self, db_session):
        """Anime movie found as Movie type in Jellyfin."""
        from app.services.jellyfin_verifier import verify_anime_movie

        request = MediaRequest(
            title="Violet Evergarden: Recollections",
            media_type=MediaType.MOVIE,
            state=RequestState.ANIME_MATCHING,
            tmdb_id=1052946,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.commit()

        # Mock Jellyfin finding as Movie
        with patch("app.services.jellyfin_verifier.jellyfin_client") as mock_client:
            mock_client.find_item_by_tmdb = AsyncMock(
                return_value={
                    "Id": "movie123",
                    "Type": "Movie",
                    "MediaSources": [{"Id": "source1"}],
                }
            )

            result = await verify_anime_movie(request, db_session)

        assert result is True
        assert request.state == RequestState.AVAILABLE
        assert request.jellyfin_id == "movie123"

    @pytest.mark.asyncio
    async def test_found_as_series_fallback(self, db_session):
        """Anime movie recategorized as Series by Shoko, found via fallback."""
        from app.services.jellyfin_verifier import verify_anime_movie

        request = MediaRequest(
            title="Violet Evergarden: Recollections",
            media_type=MediaType.MOVIE,
            state=RequestState.ANIME_MATCHING,
            tmdb_id=1052946,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.commit()

        # Mock Jellyfin: Movie not found, but Series is found
        with patch("app.services.jellyfin_verifier.jellyfin_client") as mock_client:
            # First call (Movie) returns None, second call (Series) returns item
            mock_client.find_item_by_tmdb = AsyncMock(
                side_effect=[
                    None,  # Try 1: Movie by TMDB - not found
                    {       # Try 2: Series by TMDB - found!
                        "Id": "series456",
                        "Type": "Series",
                        "MediaSources": [{"Id": "source1"}],
                    },
                ]
            )

            result = await verify_anime_movie(request, db_session)

        assert result is True
        assert request.state == RequestState.AVAILABLE
        assert request.jellyfin_id == "series456"

    @pytest.mark.asyncio
    async def test_title_search_fallback(self, db_session):
        """Anime movie found by title search as last resort."""
        from app.services.jellyfin_verifier import verify_anime_movie

        request = MediaRequest(
            title="Violet Evergarden: Recollections",
            media_type=MediaType.MOVIE,
            state=RequestState.ANIME_MATCHING,
            tmdb_id=1052946,
            year=2021,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.commit()

        with patch("app.services.jellyfin_verifier.jellyfin_client") as mock_client:
            # All TMDB lookups fail, but title search succeeds
            mock_client.find_item_by_tmdb = AsyncMock(return_value=None)
            mock_client.search_by_title = AsyncMock(
                return_value={
                    "Id": "title789",
                    "Type": "Movie",
                    "MediaSources": [{"Id": "source1"}],
                }
            )

            result = await verify_anime_movie(request, db_session)

        assert result is True
        assert request.state == RequestState.AVAILABLE
        assert request.jellyfin_id == "title789"

    @pytest.mark.asyncio
    async def test_not_found_anywhere(self, db_session):
        """Anime movie not found in Jellyfin at all."""
        from app.services.jellyfin_verifier import verify_anime_movie

        request = MediaRequest(
            title="Missing Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.ANIME_MATCHING,
            tmdb_id=999999,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.commit()

        with patch("app.services.jellyfin_verifier.jellyfin_client") as mock_client:
            mock_client.find_item_by_tmdb = AsyncMock(return_value=None)
            mock_client.search_by_title = AsyncMock(return_value=None)

            result = await verify_anime_movie(request, db_session)

        assert result is False
        # State should not change
        assert request.state == RequestState.ANIME_MATCHING


class TestShokoFileMatched:
    """Test Shoko FileMatched event handling for movies."""

    @pytest.mark.asyncio
    async def test_shoko_matched_triggers_verification(self, db_session):
        """Shoko FileMatched with cross-refs triggers Jellyfin verification."""
        from app.plugins.shoko import handle_shoko_file_matched

        @dataclass
        class MockFileEvent:
            file_id: int = 12345
            managed_folder_id: int = 1
            relative_path: str = "anime/movies/Violet Evergarden/movie.mkv"
            has_cross_references: bool = True
            event_type: str = "matched"

        # Create anime movie in IMPORTING state (will transition to ANIME_MATCHING)
        request = MediaRequest(
            title="Violet Evergarden: Recollections",
            media_type=MediaType.MOVIE,
            state=RequestState.IMPORTING,  # Start from IMPORTING
            tmdb_id=1052946,
            is_anime=True,
            final_path="/data/anime/movies/Violet Evergarden/movie.mkv",
        )
        db_session.add(request)
        await db_session.commit()

        event = MockFileEvent()

        # Mock asyncio.create_task to capture the verification call
        with patch("app.plugins.shoko.asyncio.create_task") as mock_create_task, \
             patch("app.plugins.shoko.broadcaster") as mock_broadcaster:
            mock_broadcaster.broadcast_update = AsyncMock()

            await handle_shoko_file_matched(event, db_session)
            await db_session.commit()

            # Verification task should have been created
            assert mock_create_task.called

        # Check that shoko_series_id was stored
        assert request.shoko_series_id == 12345
        # Should be in ANIME_MATCHING (transitioned from IMPORTING)
        assert request.state == RequestState.ANIME_MATCHING

    @pytest.mark.asyncio
    async def test_shoko_detected_no_crossrefs(self, db_session):
        """Shoko FileMatched without cross-refs transitions to ANIME_MATCHING."""
        from app.plugins.shoko import handle_shoko_file_matched

        @dataclass
        class MockFileEvent:
            file_id: int = 12345
            managed_folder_id: int = 1
            relative_path: str = "anime/movies/Violet Evergarden/movie.mkv"
            has_cross_references: bool = False  # Not yet matched
            event_type: str = "matched"

        # Create anime movie in IMPORTING state
        request = MediaRequest(
            title="Violet Evergarden: Recollections",
            media_type=MediaType.MOVIE,
            state=RequestState.IMPORTING,
            tmdb_id=1052946,
            is_anime=True,
            final_path="/data/anime/movies/Violet Evergarden/movie.mkv",
        )
        db_session.add(request)
        await db_session.commit()

        event = MockFileEvent()

        # Mock broadcaster to avoid errors
        with patch("app.plugins.shoko.broadcaster") as mock_broadcaster:
            mock_broadcaster.broadcast_update = AsyncMock()

            await handle_shoko_file_matched(event, db_session)
            await db_session.commit()

        # Should transition to ANIME_MATCHING (not AVAILABLE)
        assert request.state == RequestState.ANIME_MATCHING

    @pytest.mark.asyncio
    async def test_shoko_path_matching(self, db_session):
        """Shoko path correctly matches request's final_path."""
        from app.plugins.shoko import find_request_by_path, find_request_by_path_pattern

        # Create request with final_path
        request = MediaRequest(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.ANIME_MATCHING,
            final_path="/data/anime/movies/Test Movie (2024)/Test.Movie.2024.1080p.mkv",
        )
        db_session.add(request)
        await db_session.commit()

        # Test exact path match
        found = await find_request_by_path(
            db_session,
            "/data/anime/movies/Test Movie (2024)/Test.Movie.2024.1080p.mkv"
        )
        assert found is not None
        assert found.id == request.id

        # Test pattern match (by filename)
        found2 = await find_request_by_path_pattern(
            db_session,
            "anime/movies/Test Movie (2024)/Test.Movie.2024.1080p.mkv"
        )
        assert found2 is not None
        assert found2.id == request.id


class TestIsPlayable:
    """Test is_playable helper for Jellyfin items."""

    def test_playable_with_media_sources(self):
        """Item with MediaSources is playable."""
        from app.services.jellyfin_verifier import is_playable

        item = {"MediaSources": [{"Id": "123"}]}
        assert is_playable(item) is True

    def test_playable_with_path(self):
        """Item with Path is playable."""
        from app.services.jellyfin_verifier import is_playable

        item = {"Path": "/data/movies/test.mkv"}
        assert is_playable(item) is True

    def test_not_playable_without_sources_or_path(self):
        """Item without MediaSources or Path is not playable."""
        from app.services.jellyfin_verifier import is_playable

        item = {"Id": "123", "Name": "Test Movie"}
        assert is_playable(item) is False

    def test_not_playable_empty_media_sources(self):
        """Item with empty MediaSources list is not playable."""
        from app.services.jellyfin_verifier import is_playable

        item = {"MediaSources": []}
        assert is_playable(item) is False


class TestVerificationRouter:
    """Test unified verification router."""

    @pytest.mark.asyncio
    async def test_routes_anime_movie_correctly(self, db_session):
        """verify_request routes anime movie to verify_anime_movie."""
        from app.services.jellyfin_verifier import verify_request

        request = MediaRequest(
            title="Anime Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.ANIME_MATCHING,
            tmdb_id=12345,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.commit()

        with patch("app.services.jellyfin_verifier.verify_anime_movie") as mock_verify:
            mock_verify.return_value = True

            result = await verify_request(request, db_session)

            mock_verify.assert_called_once_with(request, db_session)
            assert result is True

    @pytest.mark.asyncio
    async def test_routes_regular_movie_correctly(self, db_session):
        """verify_request routes regular movie to verify_regular_movie."""
        from app.services.jellyfin_verifier import verify_request

        request = MediaRequest(
            title="Regular Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.IMPORTING,
            tmdb_id=12345,
            is_anime=False,
        )
        db_session.add(request)
        await db_session.commit()

        with patch("app.services.jellyfin_verifier.verify_regular_movie") as mock_verify:
            mock_verify.return_value = True

            result = await verify_request(request, db_session)

            mock_verify.assert_called_once_with(request, db_session)
            assert result is True
