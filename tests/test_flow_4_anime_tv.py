"""Test Flow 4: Anime TV.

Tests the complete flow for anime TV shows with per-episode tracking:
APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → ANIME_MATCHING → AVAILABLE

Key differences from regular TV:
- is_anime detected from series.type at Grab time
- Episodes go through ANIME_MATCHING instead of IMPORTING
- Shoko FileMatched events update individual episode states
- State aggregation reflects episode progress

Uses captured webhooks from docs/flows/captured-webhooks/ to test
real-world scenarios including season pack handling.
"""

import pytest
from unittest.mock import AsyncMock, patch
from dataclasses import dataclass
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import MediaRequest, MediaType, RequestState, Episode, EpisodeState
from app.plugins.jellyseerr import JellyseerrPlugin
from app.plugins.sonarr import SonarrPlugin
from app.services.state_calculator import calculate_aggregate_state, get_episode_progress


class TestAnimeDetectionTV:
    """Test anime detection from series.type."""

    @pytest.mark.asyncio
    async def test_anime_detected_from_series_type(self, db_session, load_webhook):
        """is_anime=True when series.type == 'anime'."""
        # Create request (simulating Jellyseerr)
        request = MediaRequest(
            title="Lycoris Recoil",
            media_type=MediaType.TV,
            state=RequestState.APPROVED,
            tvdb_id=414057,
        )
        db_session.add(request)
        await db_session.commit()

        # Process Sonarr Grab (which has type: "anime")
        plugin = SonarrPlugin()
        grab_payload = load_webhook("sonarr-grab")

        result = await plugin.handle_webhook(grab_payload, db_session)
        await db_session.commit()

        # The captured webhook has type: "anime"
        assert result.is_anime is True


class TestAnimeEpisodeCreation:
    """Test episode creation for anime TV."""

    @pytest.mark.asyncio
    async def test_anime_grab_creates_episodes_in_grabbing(self, db_session, load_webhook):
        """Sonarr Grab creates Episode rows in GRABBING state."""
        request = MediaRequest(
            title="Lycoris Recoil",
            media_type=MediaType.TV,
            state=RequestState.APPROVED,
            tvdb_id=414057,
        )
        db_session.add(request)
        await db_session.commit()

        plugin = SonarrPlugin()
        grab_payload = load_webhook("sonarr-grab")

        await plugin.handle_webhook(grab_payload, db_session)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        # All 13 episodes created in GRABBING state
        assert len(request.episodes) == 13
        for ep in request.episodes:
            assert ep.state == EpisodeState.GRABBING


class TestAnimeImport:
    """Test anime TV import routing to ANIME_MATCHING."""

    @pytest.mark.asyncio
    async def test_anime_import_episodes_go_to_anime_matching(self, db_session, load_webhook):
        """Anime TV episodes route to ANIME_MATCHING state after import."""
        # Create request with episodes
        request = MediaRequest(
            title="Lycoris Recoil",
            media_type=MediaType.TV,
            state=RequestState.DOWNLOADED,
            tvdb_id=414057,
            qbit_hash="3F92992E2FBEB6EBB251304236BF5E0B600A91C3",
            is_anime=True,  # Detected at grab time
        )
        db_session.add(request)
        await db_session.flush()

        # Create episodes from grab
        grab_payload = load_webhook("sonarr-grab")
        for ep_data in grab_payload.get("episodes", []):
            episode = Episode(
                request_id=request.id,
                season_number=ep_data.get("seasonNumber"),
                episode_number=ep_data.get("episodeNumber"),
                episode_title=ep_data.get("title"),
                sonarr_episode_id=ep_data.get("id"),
                qbit_hash=request.qbit_hash,
                state=EpisodeState.DOWNLOADED,
            )
            db_session.add(episode)
        await db_session.commit()

        # Process Import
        plugin = SonarrPlugin()
        import_payload = load_webhook("sonarr-import")
        await plugin.handle_webhook(import_payload, db_session)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        # All episodes should be ANIME_MATCHING (is_anime=True)
        for ep in request.episodes:
            assert ep.state == EpisodeState.ANIME_MATCHING

        # Request should also be ANIME_MATCHING (aggregated)
        assert request.state == RequestState.ANIME_MATCHING


class TestShokoEpisodeMatching:
    """Test Shoko FileMatched for individual episodes."""

    @pytest.mark.asyncio
    async def test_shoko_matches_single_episode(self, db_session):
        """Shoko FileMatched updates single episode to AVAILABLE."""
        from app.plugins.shoko import _handle_tv_episode_matched

        @dataclass
        class MockFileEvent:
            file_id: int = 12345
            managed_folder_id: int = 1
            relative_path: str = "anime/shows/Lycoris Recoil/Season 1/S01E01.mkv"
            has_cross_references: bool = True
            event_type: str = "matched"

        # Create request with episodes
        request = MediaRequest(
            title="Lycoris Recoil",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
            tvdb_id=414057,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.flush()

        # Create 3 episodes in ANIME_MATCHING state
        for i in range(3):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.ANIME_MATCHING,
                final_path=f"/data/anime/shows/Lycoris Recoil/Season 1/S01E0{i+1}.mkv",
            )
            db_session.add(ep)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        # Get episode 1
        ep1 = next(ep for ep in request.episodes if ep.episode_number == 1)

        event = MockFileEvent()

        with patch("app.plugins.shoko.broadcaster") as mock_broadcaster:
            mock_broadcaster.broadcast_update = AsyncMock()

            await _handle_tv_episode_matched(ep1, event, db_session)

        # Episode 1 should be AVAILABLE
        assert ep1.state == EpisodeState.AVAILABLE
        assert ep1.shoko_file_id == "12345"

        # Episodes 2-3 still ANIME_MATCHING
        # Request state: still ANIME_MATCHING (not all episodes available)

    @pytest.mark.asyncio
    async def test_all_episodes_available_transitions_request(self, db_session):
        """When all episodes AVAILABLE, request transitions to AVAILABLE."""
        from app.plugins.shoko import _handle_tv_episode_matched

        @dataclass
        class MockFileEvent:
            file_id: int = 99999
            managed_folder_id: int = 1
            relative_path: str = "anime/shows/Test/Season 1/S01E03.mkv"
            has_cross_references: bool = True
            event_type: str = "matched"

        # Create request with episodes
        request = MediaRequest(
            title="Test Anime",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
            tvdb_id=12345,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.flush()

        # Create 3 episodes: 2 already AVAILABLE, 1 in ANIME_MATCHING
        for i in range(2):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.AVAILABLE,  # Already done
                final_path=f"/data/anime/shows/Test/Season 1/S01E0{i+1}.mkv",
            )
            db_session.add(ep)

        last_ep = Episode(
            request_id=request.id,
            season_number=1,
            episode_number=3,
            state=EpisodeState.ANIME_MATCHING,  # Last one pending
            final_path="/data/anime/shows/Test/Season 1/S01E03.mkv",
        )
        db_session.add(last_ep)
        await db_session.commit()

        event = MockFileEvent()

        with patch("app.plugins.shoko.broadcaster") as mock_broadcaster:
            mock_broadcaster.broadcast_update = AsyncMock()

            await _handle_tv_episode_matched(last_ep, event, db_session)

        # Last episode should be AVAILABLE
        assert last_ep.state == EpisodeState.AVAILABLE

        # Reload request
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        # All episodes AVAILABLE → request AVAILABLE
        assert request.state == RequestState.AVAILABLE

    @pytest.mark.asyncio
    async def test_shoko_episode_detected_no_crossrefs(self, db_session):
        """Shoko episode detected without cross-refs stays in ANIME_MATCHING."""
        from app.plugins.shoko import _handle_tv_episode_matched

        @dataclass
        class MockFileEvent:
            file_id: int = 12345
            managed_folder_id: int = 1
            relative_path: str = "anime/shows/Test/Season 1/S01E01.mkv"
            has_cross_references: bool = False  # Not yet matched
            event_type: str = "matched"

        # Create request with episode in IMPORTING state
        request = MediaRequest(
            title="Test Anime",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.flush()

        ep = Episode(
            request_id=request.id,
            season_number=1,
            episode_number=1,
            state=EpisodeState.IMPORTING,
            final_path="/data/anime/shows/Test/Season 1/S01E01.mkv",
        )
        db_session.add(ep)
        await db_session.commit()

        event = MockFileEvent()

        with patch("app.plugins.shoko.broadcaster") as mock_broadcaster:
            mock_broadcaster.broadcast_update = AsyncMock()

            await _handle_tv_episode_matched(ep, event, db_session)

        # Episode should transition to ANIME_MATCHING
        assert ep.state == EpisodeState.ANIME_MATCHING
        assert ep.shoko_file_id == "12345"


class TestAnimeStateAggregation:
    """Test state aggregation for anime TV shows."""

    @pytest.mark.asyncio
    async def test_anime_matching_has_highest_priority(self, db_session):
        """ANIME_MATCHING has higher priority than IMPORTING."""
        request = MediaRequest(
            title="Test Anime",
            media_type=MediaType.TV,
            state=RequestState.IMPORTING,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.flush()

        # Mix of IMPORTING and ANIME_MATCHING
        for i in range(3):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.IMPORTING,
            )
            db_session.add(ep)

        ep4 = Episode(
            request_id=request.id,
            season_number=1,
            episode_number=4,
            state=EpisodeState.ANIME_MATCHING,
        )
        db_session.add(ep4)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        # Should be ANIME_MATCHING (highest priority)
        assert calculate_aggregate_state(request) == RequestState.ANIME_MATCHING

    @pytest.mark.asyncio
    async def test_mixed_anime_available_states(self, db_session):
        """Mix of ANIME_MATCHING and AVAILABLE episodes."""
        request = MediaRequest(
            title="Test Anime",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.flush()

        # 2 AVAILABLE, 1 ANIME_MATCHING
        for i in range(2):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.AVAILABLE,
            )
            db_session.add(ep)

        ep3 = Episode(
            request_id=request.id,
            season_number=1,
            episode_number=3,
            state=EpisodeState.ANIME_MATCHING,
        )
        db_session.add(ep3)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        # Not all AVAILABLE, so should be ANIME_MATCHING
        assert calculate_aggregate_state(request) == RequestState.ANIME_MATCHING

    @pytest.mark.asyncio
    async def test_all_available_returns_available(self, db_session):
        """All episodes AVAILABLE → request AVAILABLE."""
        request = MediaRequest(
            title="Test Anime",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.flush()

        # All AVAILABLE
        for i in range(5):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.AVAILABLE,
            )
            db_session.add(ep)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        assert calculate_aggregate_state(request) == RequestState.AVAILABLE


class TestAnimeEpisodeProgress:
    """Test episode progress tracking for anime TV."""

    @pytest.mark.asyncio
    async def test_get_anime_episode_progress(self, db_session):
        """get_episode_progress counts AVAILABLE episodes correctly."""
        request = MediaRequest(
            title="Test Anime",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.flush()

        # 5 AVAILABLE + 8 ANIME_MATCHING
        for i in range(5):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.AVAILABLE,
            )
            db_session.add(ep)

        for i in range(8):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 6,
                state=EpisodeState.ANIME_MATCHING,
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
        assert completed == 5
        assert total == 13


class TestAnimeTVVerification:
    """Test Jellyfin verification for anime TV."""

    @pytest.mark.asyncio
    async def test_verify_anime_tv_by_tvdb(self, db_session):
        """Anime TV verified by TVDB ID in Jellyfin."""
        from app.services.jellyfin_verifier import verify_anime_tv

        request = MediaRequest(
            title="Lycoris Recoil",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
            tvdb_id=414057,
            is_anime=True,
        )
        db_session.add(request)
        await db_session.flush()

        # Add some episodes
        for i in range(3):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.ANIME_MATCHING,
            )
            db_session.add(ep)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        with patch("app.services.jellyfin_verifier.jellyfin_client") as mock_client:
            mock_client.find_item_by_tvdb = AsyncMock(
                return_value={
                    "Id": "series123",
                    "Type": "Series",
                    "MediaSources": [{"Id": "source1"}],
                }
            )

            result = await verify_anime_tv(request, db_session)

        assert result is True
        assert request.state == RequestState.AVAILABLE
        assert request.jellyfin_id == "series123"

        # All episodes should be marked AVAILABLE
        for ep in request.episodes:
            assert ep.state == EpisodeState.AVAILABLE

    @pytest.mark.asyncio
    async def test_verify_anime_tv_title_fallback(self, db_session):
        """Anime TV found by title search as fallback."""
        from app.services.jellyfin_verifier import verify_anime_tv

        request = MediaRequest(
            title="Lycoris Recoil",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
            tvdb_id=None,  # No TVDB ID
            tmdb_id=None,  # No TMDB ID
            is_anime=True,
        )
        db_session.add(request)
        await db_session.flush()

        ep = Episode(
            request_id=request.id,
            season_number=1,
            episode_number=1,
            state=EpisodeState.ANIME_MATCHING,
        )
        db_session.add(ep)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        with patch("app.services.jellyfin_verifier.jellyfin_client") as mock_client:
            mock_client.find_item_by_tvdb = AsyncMock(return_value=None)
            mock_client.find_item_by_tmdb = AsyncMock(return_value=None)
            mock_client.search_by_title = AsyncMock(
                return_value={
                    "Id": "title456",
                    "Type": "Series",
                    "Path": "/data/anime/shows/Lycoris Recoil",
                }
            )

            result = await verify_anime_tv(request, db_session)

        assert result is True
        assert request.state == RequestState.AVAILABLE


class TestFindEpisodeByPath:
    """Test episode path matching for Shoko events."""

    @pytest.mark.asyncio
    async def test_find_episode_exact_path(self, db_session):
        """Find episode by exact path match."""
        from app.plugins.shoko import find_episode_by_path

        request = MediaRequest(
            title="Test Anime",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
        )
        db_session.add(request)
        await db_session.flush()

        ep = Episode(
            request_id=request.id,
            season_number=1,
            episode_number=5,
            state=EpisodeState.ANIME_MATCHING,
            final_path="/data/anime/shows/Test/Season 1/Test.S01E05.mkv",
        )
        db_session.add(ep)
        await db_session.commit()

        found = await find_episode_by_path(
            db_session,
            "/data/anime/shows/Test/Season 1/Test.S01E05.mkv",
            "anime/shows/Test/Season 1/Test.S01E05.mkv"
        )

        assert found is not None
        assert found.id == ep.id
        assert found.episode_number == 5

    @pytest.mark.asyncio
    async def test_find_episode_by_filename(self, db_session):
        """Find episode by filename when exact path doesn't match."""
        from app.plugins.shoko import find_episode_by_path

        request = MediaRequest(
            title="Test Anime",
            media_type=MediaType.TV,
            state=RequestState.ANIME_MATCHING,
        )
        db_session.add(request)
        await db_session.flush()

        ep = Episode(
            request_id=request.id,
            season_number=1,
            episode_number=3,
            state=EpisodeState.IMPORTING,  # Still in IMPORTING
            final_path="/data/anime/Test Anime/Season 1/Test.Anime.S01E03.mkv",
        )
        db_session.add(ep)
        await db_session.commit()

        # Different base path but same filename
        found = await find_episode_by_path(
            db_session,
            "/wrong/path/Test.Anime.S01E03.mkv",
            "different/path/Test.Anime.S01E03.mkv"
        )

        assert found is not None
        assert found.id == ep.id
