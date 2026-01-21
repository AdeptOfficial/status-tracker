"""Library sync service for importing existing media from Jellyfin.

This service handles Phase 1 of bulk media sync: syncing AVAILABLE content
from Jellyfin to the status-tracker database. It uses Jellyfin as the source
of truth and enriches entries with IDs from Radarr/Sonarr.

Flow:
1. Fetch all items from Jellyfin (source of truth for AVAILABLE)
2. Fetch existing tracked IDs from status-tracker DB
3. Filter out already-tracked items
4. Fetch all from Radarr/Sonarr for ID enrichment
5. Create AVAILABLE entries with all correlation IDs populated
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.jellyfin import jellyfin_client
from app.clients.sonarr import sonarr_client
from app.clients.radarr import radarr_client
from app.config import settings
from app.models import MediaRequest, MediaType, RequestState, TimelineEvent

logger = logging.getLogger(__name__)


@dataclass
class SyncResult:
    """Result of a library sync operation."""

    total_scanned: int = 0
    added: int = 0
    skipped: int = 0
    errors: int = 0
    error_details: list[str] = field(default_factory=list)


class LibrarySyncService:
    """
    Service for syncing existing library content to status-tracker.

    Uses Jellyfin as the source of truth for AVAILABLE status.
    Only syncs items that are actually visible in Jellyfin.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def sync_available_content(self) -> SyncResult:
        """
        Sync all available content from Jellyfin to status-tracker.

        This is Phase 1 sync: only syncs items that exist in Jellyfin
        (i.e., are actually available to watch).

        Returns:
            SyncResult with counts of added, skipped, and errored items
        """
        result = SyncResult()

        # Step 0: Trigger Jellyfin library rescan to ensure fresh data
        logger.info("Triggering Jellyfin library rescan...")
        await self._trigger_jellyfin_rescan()

        # Step 1: Fetch all items from Jellyfin
        logger.info("Fetching all items from Jellyfin...")
        jellyfin_items = await jellyfin_client.get_all_items()

        if not jellyfin_items:
            logger.warning("No items returned from Jellyfin")
            return result

        result.total_scanned = len(jellyfin_items)
        logger.info(f"Found {result.total_scanned} items in Jellyfin")

        # Step 2: Fetch existing tracked IDs from DB
        existing_tmdb_ids, existing_tvdb_ids, existing_jellyfin_ids = await self._get_existing_ids()
        logger.info(
            f"Already tracking: {len(existing_tmdb_ids)} by TMDB, "
            f"{len(existing_tvdb_ids)} by TVDB, {len(existing_jellyfin_ids)} by Jellyfin ID"
        )

        # Step 3: Fetch Radarr/Sonarr data for enrichment
        logger.info("Fetching Radarr movies for ID enrichment...")
        radarr_movies = await radarr_client.get_all_movies()
        radarr_by_tmdb = {m.get("tmdbId"): m for m in radarr_movies if m.get("tmdbId")}
        logger.info(f"Built Radarr lookup with {len(radarr_by_tmdb)} movies")

        logger.info("Fetching Sonarr series for ID enrichment...")
        sonarr_series = await sonarr_client.get_all_series()
        sonarr_by_tvdb = {s.get("tvdbId"): s for s in sonarr_series if s.get("tvdbId")}
        logger.info(f"Built Sonarr lookup with {len(sonarr_by_tvdb)} series")

        # Step 4: Process each Jellyfin item
        for item in jellyfin_items:
            try:
                sync_status = await self._process_jellyfin_item(
                    item=item,
                    existing_tmdb_ids=existing_tmdb_ids,
                    existing_tvdb_ids=existing_tvdb_ids,
                    existing_jellyfin_ids=existing_jellyfin_ids,
                    radarr_by_tmdb=radarr_by_tmdb,
                    sonarr_by_tvdb=sonarr_by_tvdb,
                )

                if sync_status == "added":
                    result.added += 1
                elif sync_status == "skipped":
                    result.skipped += 1
                # "error" case handled in exception

            except Exception as e:
                result.errors += 1
                error_msg = f"Error processing '{item.get('Name', 'Unknown')}': {e}"
                result.error_details.append(error_msg)
                logger.error(error_msg)

        # Commit all changes
        await self.db.commit()

        logger.info(
            f"Sync complete: {result.added} added, {result.skipped} skipped, "
            f"{result.errors} errors"
        )

        return result

    async def _get_existing_ids(self) -> tuple[set[int], set[int], set[str]]:
        """
        Fetch existing tracked IDs from the database.

        Returns:
            Tuple of (tmdb_ids, tvdb_ids, jellyfin_ids) sets
        """
        stmt = select(
            MediaRequest.tmdb_id,
            MediaRequest.tvdb_id,
            MediaRequest.jellyfin_id
        )
        result = await self.db.execute(stmt)
        rows = result.all()

        tmdb_ids = {r[0] for r in rows if r[0] is not None}
        tvdb_ids = {r[1] for r in rows if r[1] is not None}
        jellyfin_ids = {r[2] for r in rows if r[2] is not None}

        return tmdb_ids, tvdb_ids, jellyfin_ids

    async def _process_jellyfin_item(
        self,
        item: dict,
        existing_tmdb_ids: set[int],
        existing_tvdb_ids: set[int],
        existing_jellyfin_ids: set[str],
        radarr_by_tmdb: dict[int, dict],
        sonarr_by_tvdb: dict[int, dict],
    ) -> str:
        """
        Process a single Jellyfin item for sync.

        Args:
            item: Jellyfin item data
            existing_*: Sets of already-tracked IDs
            radarr_by_tmdb: Lookup dict for Radarr movies by TMDB ID
            sonarr_by_tvdb: Lookup dict for Sonarr series by TVDB ID

        Returns:
            "added", "skipped", or raises exception on error
        """
        jellyfin_id = item.get("Id")
        item_type = item.get("Type")  # "Movie" or "Series"
        title = item.get("Name", "Unknown")
        provider_ids = item.get("ProviderIds", {})

        # Extract provider IDs (Jellyfin uses string keys)
        tmdb_id = self._parse_int(provider_ids.get("Tmdb"))
        tvdb_id = self._parse_int(provider_ids.get("Tvdb"))
        imdb_id = provider_ids.get("Imdb")  # Keep as string

        # Check if already tracked (by any ID)
        if jellyfin_id and jellyfin_id in existing_jellyfin_ids:
            return "skipped"
        if tmdb_id and tmdb_id in existing_tmdb_ids:
            return "skipped"
        if tvdb_id and tvdb_id in existing_tvdb_ids:
            return "skipped"

        # Determine media type
        if item_type == "Movie":
            media_type = MediaType.MOVIE
        elif item_type == "Series":
            media_type = MediaType.TV
        else:
            logger.debug(f"Skipping unsupported item type: {item_type} for '{title}'")
            return "skipped"

        # Enrich with Radarr/Sonarr IDs
        radarr_id = None
        sonarr_id = None

        if media_type == MediaType.MOVIE and tmdb_id:
            radarr_movie = radarr_by_tmdb.get(tmdb_id)
            if radarr_movie:
                radarr_id = radarr_movie.get("id")

        if media_type == MediaType.TV and tvdb_id:
            sonarr_show = sonarr_by_tvdb.get(tvdb_id)
            if sonarr_show:
                sonarr_id = sonarr_show.get("id")

        # Extract additional metadata
        year = item.get("ProductionYear")
        # Jellyfin may have poster as ImageTags or PrimaryImageTag
        # Use the external JELLYFIN_URL for user-facing links
        poster_url = None
        if item.get("ImageTags", {}).get("Primary"):
            poster_url = f"{settings.JELLYFIN_URL}/Items/{jellyfin_id}/Images/Primary"

        # Create the request entry
        request = MediaRequest(
            title=title,
            media_type=media_type,
            state=RequestState.AVAILABLE,
            jellyfin_id=jellyfin_id,
            tmdb_id=tmdb_id,
            tvdb_id=tvdb_id,
            radarr_id=radarr_id,
            sonarr_id=sonarr_id,
            year=year,
            poster_url=poster_url,
            requested_by="Library Sync",
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
            state_changed_at=datetime.utcnow(),
        )

        self.db.add(request)
        await self.db.flush()  # Get the ID for timeline event

        # Add timeline event
        timeline_event = TimelineEvent(
            request_id=request.id,
            service="library_sync",
            event_type="Import",
            state=RequestState.AVAILABLE,
            details=f"Synced from Jellyfin library",
            timestamp=datetime.utcnow(),
        )
        self.db.add(timeline_event)

        # Update existing_ids sets to prevent duplicates within this sync
        if jellyfin_id:
            existing_jellyfin_ids.add(jellyfin_id)
        if tmdb_id:
            existing_tmdb_ids.add(tmdb_id)
        if tvdb_id:
            existing_tvdb_ids.add(tvdb_id)

        logger.debug(f"Added: {title} ({media_type.value})")
        return "added"

    @staticmethod
    def _parse_int(value) -> int | None:
        """Safely parse a value to int, returning None if invalid."""
        if value is None:
            return None
        try:
            return int(value)
        except (ValueError, TypeError):
            return None

    async def _trigger_jellyfin_rescan(self) -> bool:
        """
        Trigger a Jellyfin library rescan before fetching items.

        This ensures we get the most up-to-date library state.
        Note: This triggers an async scan - Jellyfin processes it in background.
        We don't wait for completion as the /Items endpoint will return
        whatever is currently indexed.

        Returns:
            True if rescan was triggered successfully
        """
        try:
            success = await jellyfin_client.trigger_library_scan()
            if not success:
                logger.warning("Jellyfin rescan trigger returned false, continuing anyway")
            return success
        except Exception as e:
            logger.warning(f"Failed to trigger Jellyfin rescan: {e}")
            # Continue anyway - sync will work with current library state
            return False
