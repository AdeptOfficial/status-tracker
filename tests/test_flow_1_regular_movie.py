"""Test Flow 1: Regular Movie.

Tests the complete flow for a regular (non-anime) movie:
APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE

Uses captured webhooks from docs/flows/captured-webhooks/ to test
real-world scenarios.
"""

import pytest
from unittest.mock import AsyncMock, patch

from app.models import MediaRequest, MediaType, RequestState
from app.plugins.jellyseerr import JellyseerrPlugin
from app.plugins.radarr import RadarrPlugin
from app.core.correlator import correlator
from app.core.state_machine import state_machine


class TestJellyseerrWebhook:
    """Test Jellyseerr webhook creates request with correct data."""

    @pytest.mark.asyncio
    async def test_movie_auto_approved_creates_request(self, db_session, load_webhook):
        """MEDIA_AUTO_APPROVED creates request in APPROVED state."""
        plugin = JellyseerrPlugin()
        payload = load_webhook("jellyseerr-movie-auto-approved")

        request = await plugin.handle_webhook(payload, db_session)
        await db_session.commit()

        assert request is not None
        assert request.state == RequestState.APPROVED
        assert request.media_type == MediaType.MOVIE
        assert request.tmdb_id == 533514  # From captured webhook
        assert request.jellyseerr_id is not None  # Just verify it's set

    @pytest.mark.asyncio
    async def test_poster_url_extracted(self, db_session, load_webhook):
        """Poster URL extracted from payload.image (not extra array)."""
        plugin = JellyseerrPlugin()
        payload = load_webhook("jellyseerr-movie-auto-approved")

        request = await plugin.handle_webhook(payload, db_session)

        assert request.poster_url is not None
        assert "themoviedb.org" in request.poster_url or "image.tmdb.org" in request.poster_url

    @pytest.mark.asyncio
    async def test_overview_extracted(self, db_session, load_webhook):
        """Overview extracted from payload.message."""
        plugin = JellyseerrPlugin()
        payload = load_webhook("jellyseerr-movie-auto-approved")

        request = await plugin.handle_webhook(payload, db_session)

        # Overview comes from message field
        assert request.overview is not None
        assert len(request.overview) > 10  # Has actual content

    @pytest.mark.asyncio
    async def test_year_parsed_from_subject(self, db_session, load_webhook):
        """Year parsed from subject like 'Movie Name (2024)'."""
        plugin = JellyseerrPlugin()
        payload = load_webhook("jellyseerr-movie-auto-approved")

        request = await plugin.handle_webhook(payload, db_session)

        # Year should be extracted from subject
        assert request.year is not None
        assert request.year > 2000  # Sanity check

    @pytest.mark.asyncio
    async def test_title_without_year(self, db_session, load_webhook):
        """Title extracted without the year suffix."""
        plugin = JellyseerrPlugin()
        payload = load_webhook("jellyseerr-movie-auto-approved")

        request = await plugin.handle_webhook(payload, db_session)

        # Title should not end with (YYYY)
        assert not request.title.endswith(")")


class TestRadarrGrab:
    """Test Radarr Grab webhook handling."""

    @pytest.mark.asyncio
    async def test_grab_sets_qbit_hash(self, db_session, load_webhook):
        """Radarr Grab stores downloadId as qbit_hash."""
        # Create request first (simulating Jellyseerr webhook)
        request = MediaRequest(
            title="The Tunnel to Summer, the Exit of Goodbyes",
            media_type=MediaType.MOVIE,
            state=RequestState.APPROVED,
            tmdb_id=533514,
        )
        db_session.add(request)
        await db_session.commit()

        # Process Radarr Grab
        plugin = RadarrPlugin()
        grab_payload = load_webhook("radarr-grab")

        result = await plugin.handle_webhook(grab_payload, db_session)
        await db_session.commit()

        assert result is not None
        assert result.qbit_hash is not None
        # qBit hash should be uppercase hex
        assert result.qbit_hash == result.qbit_hash.upper()
        assert len(result.qbit_hash) == 40  # SHA1 hash length

    @pytest.mark.asyncio
    async def test_grab_transitions_to_grabbing(self, db_session, load_webhook):
        """Radarr Grab transitions request to GRABBING state."""
        request = MediaRequest(
            title="The Tunnel to Summer, the Exit of Goodbyes",
            media_type=MediaType.MOVIE,
            state=RequestState.APPROVED,
            tmdb_id=533514,
        )
        db_session.add(request)
        await db_session.commit()

        plugin = RadarrPlugin()
        grab_payload = load_webhook("radarr-grab")

        result = await plugin.handle_webhook(grab_payload, db_session)
        await db_session.commit()

        assert result.state == RequestState.GRABBING

    @pytest.mark.asyncio
    async def test_grab_detects_anime_from_tags(self, db_session, load_webhook):
        """is_anime detected from movie.tags containing 'anime'."""
        request = MediaRequest(
            title="The Tunnel to Summer, the Exit of Goodbyes",
            media_type=MediaType.MOVIE,
            state=RequestState.APPROVED,
            tmdb_id=533514,
        )
        db_session.add(request)
        await db_session.commit()

        plugin = RadarrPlugin()
        grab_payload = load_webhook("radarr-grab")

        result = await plugin.handle_webhook(grab_payload, db_session)
        await db_session.commit()

        # The captured webhook has anime tag
        assert result.is_anime is True

    @pytest.mark.asyncio
    async def test_grab_extracts_release_info(self, db_session, load_webhook):
        """Radarr Grab extracts quality, indexer, file_size, release_group."""
        request = MediaRequest(
            title="The Tunnel to Summer, the Exit of Goodbyes",
            media_type=MediaType.MOVIE,
            state=RequestState.APPROVED,
            tmdb_id=533514,
        )
        db_session.add(request)
        await db_session.commit()

        plugin = RadarrPlugin()
        grab_payload = load_webhook("radarr-grab")

        result = await plugin.handle_webhook(grab_payload, db_session)
        await db_session.commit()

        assert result.quality is not None
        assert result.indexer is not None
        # file_size and release_group may be None depending on webhook content


class TestRadarrImport:
    """Test Radarr Import (Download) webhook handling."""

    @pytest.mark.asyncio
    async def test_import_stores_final_path(self, db_session, load_webhook):
        """Radarr Import stores movieFile.path as final_path."""
        # Use TMDB ID from radarr-import.json webhook (1052946)
        request = MediaRequest(
            title="Violet Evergarden: Recollections",
            media_type=MediaType.MOVIE,
            state=RequestState.DOWNLOADED,
            tmdb_id=1052946,  # Must match webhook's movie.tmdbId
            is_anime=True,
        )
        db_session.add(request)
        await db_session.commit()

        plugin = RadarrPlugin()
        import_payload = load_webhook("radarr-import")

        result = await plugin.handle_webhook(import_payload, db_session)
        await db_session.commit()

        assert result is not None
        assert result.final_path is not None
        assert ".mkv" in result.final_path or ".mp4" in result.final_path or "/" in result.final_path

    @pytest.mark.asyncio
    async def test_import_anime_goes_to_anime_matching(self, db_session, load_webhook):
        """Anime movie routes to ANIME_MATCHING state after import."""
        # Use TMDB ID from radarr-import.json webhook
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
    async def test_import_non_anime_goes_to_importing(self, db_session, load_webhook):
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


class TestCorrelation:
    """Test request correlation logic."""

    @pytest.mark.asyncio
    async def test_correlation_excludes_available(self, db_session):
        """Old AVAILABLE requests should NOT match new webhooks."""
        # Create old AVAILABLE request
        old_request = MediaRequest(
            title="Old Request",
            media_type=MediaType.MOVIE,
            state=RequestState.AVAILABLE,
            tmdb_id=533514,
        )
        db_session.add(old_request)
        await db_session.commit()

        # Search for correlation - should NOT find old available request
        found = await correlator.find_by_any(db_session, tmdb_id=533514)

        # Should return None because AVAILABLE is excluded from active states
        assert found is None

    @pytest.mark.asyncio
    async def test_correlation_finds_active_request(self, db_session):
        """Active requests (APPROVED, GRABBING, etc.) should be found."""
        # Create active request
        active_request = MediaRequest(
            title="Active Request",
            media_type=MediaType.MOVIE,
            state=RequestState.GRABBING,
            tmdb_id=533514,
        )
        db_session.add(active_request)
        await db_session.commit()

        # Search for correlation - should find active request
        found = await correlator.find_by_any(db_session, tmdb_id=533514)

        assert found is not None
        assert found.id == active_request.id

    @pytest.mark.asyncio
    async def test_correlation_by_qbit_hash(self, db_session):
        """Requests can be found by qbit_hash."""
        request = MediaRequest(
            title="Test Request",
            media_type=MediaType.MOVIE,
            state=RequestState.GRABBING,
            qbit_hash="ABC123DEF456789012345678901234567890ABCD",
        )
        db_session.add(request)
        await db_session.commit()

        found = await correlator.find_by_any(
            db_session,
            qbit_hash="ABC123DEF456789012345678901234567890ABCD"
        )

        assert found is not None
        assert found.id == request.id


class TestStateCalculator:
    """Test state aggregation for TV shows."""

    @pytest.mark.asyncio
    async def test_movie_returns_current_state(self, db_session):
        """Movies return their current state (no aggregation)."""
        from app.services.state_calculator import calculate_aggregate_state

        request = MediaRequest(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.IMPORTING,
        )
        db_session.add(request)
        await db_session.commit()

        result = calculate_aggregate_state(request)

        assert result == RequestState.IMPORTING

    @pytest.mark.asyncio
    async def test_episode_progress(self, db_session):
        """Episode progress calculation."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from app.models import Episode, EpisodeState
        from app.services.state_calculator import get_episode_progress

        request = MediaRequest(
            title="Test Show",
            media_type=MediaType.TV,
            state=RequestState.IMPORTING,
        )
        db_session.add(request)
        await db_session.flush()

        # Add episodes with mixed states
        for i in range(10):
            state = EpisodeState.AVAILABLE if i < 3 else EpisodeState.IMPORTING
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=state,
            )
            db_session.add(ep)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        completed, total = get_episode_progress(request)

        assert completed == 3
        assert total == 10


class TestIsPlayable:
    """Test is_playable helper function."""

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
