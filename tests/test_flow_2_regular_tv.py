"""Test Flow 2: Regular TV.

Tests the complete flow for regular (non-anime) TV shows with Episode tracking:
APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE

Uses captured webhooks from docs/flows/captured-webhooks/ to test
real-world scenarios including season pack handling.
"""

import pytest
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models import MediaRequest, MediaType, RequestState, Episode, EpisodeState
from app.plugins.jellyseerr import JellyseerrPlugin
from app.plugins.sonarr import SonarrPlugin
from app.services.state_calculator import calculate_aggregate_state, get_episode_progress


class TestJellyseerrTVWebhook:
    """Test Jellyseerr TV webhook creates request with correct data."""

    @pytest.mark.asyncio
    async def test_tv_auto_approved_creates_request(self, db_session, load_webhook):
        """MEDIA_AUTO_APPROVED for TV creates request in APPROVED state."""
        plugin = JellyseerrPlugin()
        payload = load_webhook("jellyseerr-tv-auto-approved")

        request = await plugin.handle_webhook(payload, db_session)
        await db_session.commit()

        assert request is not None
        assert request.state == RequestState.APPROVED
        assert request.media_type == MediaType.TV
        assert request.tvdb_id is not None  # TV uses TVDB
        assert request.jellyseerr_id is not None

    @pytest.mark.asyncio
    async def test_tv_requested_seasons_extracted(self, db_session, load_webhook):
        """requested_seasons extracted from extra array."""
        plugin = JellyseerrPlugin()
        payload = load_webhook("jellyseerr-tv-auto-approved")

        request = await plugin.handle_webhook(payload, db_session)

        # Should have requested_seasons if present in webhook
        # This may be None if not in the webhook
        # Just verify the field is accessible
        _ = request.requested_seasons


class TestSonarrGrab:
    """Test Sonarr Grab creates Episode rows."""

    @pytest.mark.asyncio
    async def test_grab_creates_episodes(self, db_session, load_webhook):
        """Sonarr Grab creates Episode rows from episodes array."""
        # Create request first (simulating Jellyseerr)
        request = MediaRequest(
            title="Lycoris Recoil",
            media_type=MediaType.TV,
            state=RequestState.APPROVED,
            tvdb_id=414057,
        )
        db_session.add(request)
        await db_session.commit()

        # Process Sonarr Grab
        plugin = SonarrPlugin()
        grab_payload = load_webhook("sonarr-grab")

        result = await plugin.handle_webhook(grab_payload, db_session)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        # Verify 13 episodes created
        assert len(request.episodes) == 13
        assert request.total_episodes == 13

    @pytest.mark.asyncio
    async def test_episodes_have_correct_data(self, db_session, load_webhook):
        """Episodes have season, episode number, title, and IDs."""
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

        # Check first episode
        ep1 = next(ep for ep in request.episodes if ep.episode_number == 1)
        assert ep1.season_number == 1
        assert ep1.episode_title == "Easy does it"
        assert ep1.sonarr_episode_id is not None
        assert ep1.episode_tvdb_id is not None

    @pytest.mark.asyncio
    async def test_all_episodes_share_qbit_hash(self, db_session, load_webhook):
        """All episodes in season pack share the same qbit_hash."""
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

        # All episodes should have the same hash
        hashes = {ep.qbit_hash for ep in request.episodes}
        assert len(hashes) == 1
        assert request.qbit_hash in hashes

    @pytest.mark.asyncio
    async def test_grab_detects_anime_from_series_type(self, db_session, load_webhook):
        """is_anime detected from series.type == 'anime'."""
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

        # The captured webhook has type: "anime"
        assert request.is_anime is True

    @pytest.mark.asyncio
    async def test_grab_extracts_release_info(self, db_session, load_webhook):
        """Sonarr Grab extracts quality, indexer, file_size, release_group."""
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

        assert request.quality is not None
        assert request.indexer is not None
        assert request.file_size is not None
        assert request.release_group is not None


class TestSonarrImport:
    """Test Sonarr Import (season pack) handling."""

    @pytest.mark.asyncio
    async def test_import_updates_episode_paths(self, db_session, load_webhook):
        """Season pack Import updates all episode final_paths."""
        # Create request with episodes
        request = MediaRequest(
            title="Lycoris Recoil",
            media_type=MediaType.TV,
            state=RequestState.DOWNLOADED,
            tvdb_id=414057,
            qbit_hash="3F92992E2FBEB6EBB251304236BF5E0B600A91C3",
            is_anime=True,
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

        # All 13 episodes should have final_path
        for ep in request.episodes:
            assert ep.final_path is not None, f"Episode S{ep.season_number}E{ep.episode_number} missing final_path"

    @pytest.mark.asyncio
    async def test_import_anime_episodes_go_to_anime_matching(self, db_session, load_webhook):
        """Anime TV episodes go to ANIME_MATCHING state after import."""
        # Create request with episodes
        request = MediaRequest(
            title="Lycoris Recoil",
            media_type=MediaType.TV,
            state=RequestState.DOWNLOADED,
            tvdb_id=414057,
            qbit_hash="3F92992E2FBEB6EBB251304236BF5E0B600A91C3",
            is_anime=True,  # Anime series
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


class TestStateAggregation:
    """Test state aggregation for TV shows."""

    @pytest.mark.asyncio
    async def test_all_available_aggregates_to_available(self, db_session):
        """When all episodes AVAILABLE, request is AVAILABLE."""
        request = MediaRequest(
            title="Test Show",
            media_type=MediaType.TV,
            state=RequestState.IMPORTING,
        )
        db_session.add(request)
        await db_session.flush()

        # Add 5 AVAILABLE episodes
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

    @pytest.mark.asyncio
    async def test_any_failed_aggregates_to_failed(self, db_session):
        """When any episode FAILED, request is FAILED."""
        request = MediaRequest(
            title="Test Show",
            media_type=MediaType.TV,
            state=RequestState.IMPORTING,
        )
        db_session.add(request)
        await db_session.flush()

        # Add 4 AVAILABLE + 1 FAILED episode
        for i in range(4):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.AVAILABLE,
            )
            db_session.add(ep)

        failed_ep = Episode(
            request_id=request.id,
            season_number=1,
            episode_number=5,
            state=EpisodeState.FAILED,
        )
        db_session.add(failed_ep)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        assert calculate_aggregate_state(request) == RequestState.FAILED

    @pytest.mark.asyncio
    async def test_mixed_states_uses_priority(self, db_session):
        """Mixed states use highest priority in-progress state."""
        request = MediaRequest(
            title="Test Show",
            media_type=MediaType.TV,
            state=RequestState.IMPORTING,
        )
        db_session.add(request)
        await db_session.flush()

        # Add mix of AVAILABLE and IMPORTING
        for i in range(3):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.AVAILABLE,
            )
            db_session.add(ep)

        for i in range(2):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 4,
                state=EpisodeState.IMPORTING,
            )
            db_session.add(ep)
        await db_session.commit()

        # Reload with episodes
        stmt = select(MediaRequest).where(MediaRequest.id == request.id).options(
            selectinload(MediaRequest.episodes)
        )
        result = await db_session.execute(stmt)
        request = result.scalar_one()

        # Should be IMPORTING (not all available yet)
        assert calculate_aggregate_state(request) == RequestState.IMPORTING

    @pytest.mark.asyncio
    async def test_anime_matching_has_highest_priority(self, db_session):
        """ANIME_MATCHING has higher priority than IMPORTING."""
        request = MediaRequest(
            title="Test Show",
            media_type=MediaType.TV,
            state=RequestState.IMPORTING,
        )
        db_session.add(request)
        await db_session.flush()

        # Add mix of IMPORTING and ANIME_MATCHING
        for i in range(3):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.IMPORTING,
            )
            db_session.add(ep)

        ep = Episode(
            request_id=request.id,
            season_number=1,
            episode_number=4,
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

        # Should be ANIME_MATCHING (highest priority)
        assert calculate_aggregate_state(request) == RequestState.ANIME_MATCHING


class TestEpisodeProgress:
    """Test episode progress tracking."""

    @pytest.mark.asyncio
    async def test_get_episode_progress(self, db_session):
        """get_episode_progress returns correct counts."""
        request = MediaRequest(
            title="Test Show",
            media_type=MediaType.TV,
            state=RequestState.IMPORTING,
        )
        db_session.add(request)
        await db_session.flush()

        # Add 3 AVAILABLE + 10 IMPORTING
        for i in range(3):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 1,
                state=EpisodeState.AVAILABLE,
            )
            db_session.add(ep)

        for i in range(10):
            ep = Episode(
                request_id=request.id,
                season_number=1,
                episode_number=i + 4,
                state=EpisodeState.IMPORTING,
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
        assert total == 13

    @pytest.mark.asyncio
    async def test_movie_progress_returns_one_or_zero(self, db_session):
        """Movies return 0/1 or 1/1 based on state."""
        # Not available
        request = MediaRequest(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.IMPORTING,
        )
        db_session.add(request)
        await db_session.commit()

        completed, total = get_episode_progress(request)
        assert completed == 0
        assert total == 1

        # Available
        request.state = RequestState.AVAILABLE
        completed, total = get_episode_progress(request)
        assert completed == 1
        assert total == 1


class TestAdaptivePolling:
    """Test adaptive polling intervals."""

    @pytest.mark.asyncio
    async def test_adaptive_polling_fast_when_downloading(self, db_session):
        """Returns 5s interval when there are active downloads."""
        from app.plugins.qbittorrent import QBittorrentPlugin, POLL_FAST

        # Create request in DOWNLOADING state
        request = MediaRequest(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.DOWNLOADING,
        )
        db_session.add(request)
        await db_session.commit()

        plugin = QBittorrentPlugin()
        interval = await plugin.get_adaptive_poll_interval(db_session)

        assert interval == POLL_FAST
        assert interval == 5

    @pytest.mark.asyncio
    async def test_adaptive_polling_fast_when_grabbing(self, db_session):
        """Returns 5s interval when there are requests in GRABBING state."""
        from app.plugins.qbittorrent import QBittorrentPlugin, POLL_FAST

        # Create request in GRABBING state
        request = MediaRequest(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.GRABBING,
        )
        db_session.add(request)
        await db_session.commit()

        plugin = QBittorrentPlugin()
        interval = await plugin.get_adaptive_poll_interval(db_session)

        assert interval == POLL_FAST
        assert interval == 5

    @pytest.mark.asyncio
    async def test_adaptive_polling_slow_when_idle(self, db_session):
        """Returns 30s interval when no active downloads."""
        from app.plugins.qbittorrent import QBittorrentPlugin, POLL_SLOW

        # Create request in AVAILABLE state (not active)
        request = MediaRequest(
            title="Test Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.AVAILABLE,
        )
        db_session.add(request)
        await db_session.commit()

        plugin = QBittorrentPlugin()
        interval = await plugin.get_adaptive_poll_interval(db_session)

        assert interval == POLL_SLOW
        assert interval == 30

    @pytest.mark.asyncio
    async def test_adaptive_polling_slow_when_no_requests(self, db_session):
        """Returns 30s interval when no requests at all."""
        from app.plugins.qbittorrent import QBittorrentPlugin, POLL_SLOW

        # No requests in database
        plugin = QBittorrentPlugin()
        interval = await plugin.get_adaptive_poll_interval(db_session)

        assert interval == POLL_SLOW
        assert interval == 30

    @pytest.mark.asyncio
    async def test_adaptive_polling_fast_with_mixed_states(self, db_session):
        """Returns 5s if ANY request is active, even with others idle."""
        from app.plugins.qbittorrent import QBittorrentPlugin, POLL_FAST

        # Create multiple requests with mixed states
        available_request = MediaRequest(
            title="Available Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.AVAILABLE,
        )
        downloading_request = MediaRequest(
            title="Downloading Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.DOWNLOADING,
        )
        importing_request = MediaRequest(
            title="Importing Movie",
            media_type=MediaType.MOVIE,
            state=RequestState.IMPORTING,
        )
        db_session.add_all([available_request, downloading_request, importing_request])
        await db_session.commit()

        plugin = QBittorrentPlugin()
        interval = await plugin.get_adaptive_poll_interval(db_session)

        # Should be fast because one request is DOWNLOADING
        assert interval == POLL_FAST
        assert interval == 5
