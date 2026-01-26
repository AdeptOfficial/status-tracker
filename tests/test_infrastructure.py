"""Test infrastructure verification.

These tests verify that the test fixtures work correctly.
"""

import pytest
from pathlib import Path

from app.models import MediaRequest, MediaType, RequestState, Episode, EpisodeState


class TestDatabaseFixture:
    """Verify database fixture works."""

    @pytest.mark.asyncio
    async def test_db_session_creates_tables(self, db_session):
        """Database session should have all tables created."""
        # Create a simple request
        request = MediaRequest(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.REQUESTED,
        )
        db_session.add(request)
        await db_session.commit()

        # Verify it was persisted
        assert request.id is not None
        assert request.title == "Test Movie"

    @pytest.mark.asyncio
    async def test_db_session_isolates_tests(self, db_session):
        """Each test should get a fresh database."""
        from sqlalchemy import select

        # Query for any existing requests
        result = await db_session.execute(select(MediaRequest))
        requests = result.scalars().all()

        # Should be empty (isolation from previous test)
        assert len(requests) == 0

    @pytest.mark.asyncio
    async def test_episode_table_works(self, db_session):
        """Episode table should be created and linked to request."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload

        # Create a TV request
        request = MediaRequest(
            title="Test Show",
            media_type=MediaType.TV,
            state=RequestState.GRABBING,
            tvdb_id=12345,
        )
        db_session.add(request)
        await db_session.commit()

        # Create episodes
        for i in range(3):
            episode = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                episode_title=f"Episode {i + 1}",
                qbit_hash="ABC123",
                state=EpisodeState.GRABBING,
            )
            db_session.add(episode)
        await db_session.commit()

        # Verify relationship (must eagerly load for async)
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(selectinload(MediaRequest.episodes))
        result = await db_session.execute(stmt)
        loaded_request = result.scalar_one()

        assert len(loaded_request.episodes) == 3
        assert loaded_request.episodes[0].episode_title == "Episode 1"
        assert loaded_request.episodes[0].state == EpisodeState.GRABBING

    @pytest.mark.asyncio
    async def test_new_request_fields(self, db_session):
        """New fields on MediaRequest should work."""
        request = MediaRequest(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.GRABBING,
            is_anime=True,
            imdb_id="tt1234567",
            file_size=1000000000,
            release_group="TestGroup",
            overview="Test overview text",
        )
        db_session.add(request)
        await db_session.commit()

        assert request.is_anime is True
        assert request.imdb_id == "tt1234567"
        assert request.file_size == 1000000000
        assert request.release_group == "TestGroup"
        assert request.overview == "Test overview text"


class TestWebhookFixture:
    """Verify webhook loading fixture works."""

    def test_load_webhook_exists(self, load_webhook, webhook_dir):
        """Webhook fixtures directory should exist."""
        assert webhook_dir.exists(), f"Webhooks dir not found: {webhook_dir}"

    def test_load_jellyseerr_movie(self, load_webhook):
        """Should load Jellyseerr movie webhook."""
        payload = load_webhook("jellyseerr-movie-auto-approved")
        assert "notification_type" in payload
        assert payload.get("media", {}).get("media_type") == "movie"

    def test_load_jellyseerr_tv(self, load_webhook):
        """Should load Jellyseerr TV webhook."""
        payload = load_webhook("jellyseerr-tv-auto-approved")
        assert "notification_type" in payload
        assert payload.get("media", {}).get("media_type") == "tv"

    def test_load_radarr_grab(self, load_webhook):
        """Should load Radarr Grab webhook."""
        payload = load_webhook("radarr-grab")
        assert payload.get("eventType") == "Grab"
        assert "movie" in payload
        assert "downloadId" in payload

    def test_load_sonarr_grab(self, load_webhook):
        """Should load Sonarr Grab webhook."""
        payload = load_webhook("sonarr-grab")
        assert payload.get("eventType") == "Grab"
        assert "series" in payload
        assert "episodes" in payload
        assert "downloadId" in payload

    def test_load_radarr_import(self, load_webhook):
        """Should load Radarr Import webhook."""
        payload = load_webhook("radarr-import")
        assert payload.get("eventType") == "Download"
        assert "movieFile" in payload

    def test_load_sonarr_import(self, load_webhook):
        """Should load Sonarr Import webhook."""
        payload = load_webhook("sonarr-import")
        assert payload.get("eventType") == "Download"
        # Season pack has episodeFiles (plural)
        assert "episodeFiles" in payload or "episodeFile" in payload

    def test_load_nonexistent_raises(self, load_webhook):
        """Should raise FileNotFoundError for missing webhooks."""
        with pytest.raises(FileNotFoundError):
            load_webhook("nonexistent-webhook")


class TestMocks:
    """Verify mock clients work."""

    def test_mock_qbittorrent(self):
        """Mock qBittorrent client should work."""
        from tests.mocks import MockQBittorrentClient

        client = MockQBittorrentClient()
        client.add_torrent("ABC123", progress=0.5)

        assert "ABC123" in client.torrents
        assert client.torrents["ABC123"]["progress"] == 0.5

    def test_mock_jellyfin(self):
        """Mock Jellyfin client should work."""
        from tests.mocks import MockJellyfinClient

        client = MockJellyfinClient()
        client.add_item(tmdb_id=533514, item_type="Movie", jellyfin_id="test-id")

        assert len(client.items) == 1
        assert client.items[0]["ProviderIds"]["Tmdb"] == "533514"

    def test_mock_shoko(self):
        """Mock Shoko client should work."""
        from tests.mocks import MockShokoClient

        client = MockShokoClient()
        client.add_file_match("/data/anime/movies/Test/file.mkv", file_id=123)

        event = client.create_file_matched_event("/data/anime/movies/Test/file.mkv")
        assert event is not None
        assert event["EventType"] == "FileMatched"
