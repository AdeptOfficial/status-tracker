"""Shokofin VFS (Virtual File System) utilities.

Handles detection and recovery when Shokofin's VFS doesn't sync properly
with Shoko's matched files.

Problem: Shoko matches a file via SignalR, but Shokofin's VFS doesn't
create an entry. The request gets stuck in ANIME_MATCHING forever.

Solution: After N minutes stuck, delete VFS folder and trigger library
refresh to force Shokofin to rebuild with all matched files.
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Optional

import httpx

from app.config import settings

if TYPE_CHECKING:
    from app.models import MediaRequest, MediaType

logger = logging.getLogger(__name__)

# VFS rebuild cooldown - don't rebuild more than once per this interval
VFS_REBUILD_COOLDOWN_MINUTES = 10

# Time to wait after requesting library refresh for VFS to regenerate
VFS_REGENERATION_WAIT_SECONDS = 15

# Shokofin VFS library IDs (from Jellyfin library configuration)
# These are the Jellyfin library GUIDs that use Shokofin VFS
SHOKOFIN_VFS_LIBRARIES = {
    "movie": "abebc196-cc1b-8bbf-6f8b-b5ca7b5ad6f1",  # Anime Movies
    "tv": "29391378-c411-8b35-b77f-84980d25f0a6",     # Anime Shows
}

# Base path for VFS inside Jellyfin container
VFS_BASE_PATH = "/config/Shokofin/VFS"


async def check_vfs_entry_exists(request: "MediaRequest") -> bool:
    """Check if Shokofin VFS has an entry for this request.

    Uses docker exec to check if a folder matching the request exists
    in the appropriate VFS directory.

    Returns:
        True if VFS entry exists, False otherwise
    """
    from app.models import MediaType

    library_type = "movie" if request.media_type == MediaType.MOVIE else "tv"
    library_id = SHOKOFIN_VFS_LIBRARIES.get(library_type)

    if not library_id:
        logger.warning(f"No VFS library ID configured for type: {library_type}")
        return False

    vfs_path = f"{VFS_BASE_PATH}/{library_id}"

    # Use title for matching - Shokofin uses romaji/Japanese titles from Shoko
    # We'll check if ANY folder exists (VFS should have entries if working)
    try:
        # Execute ls inside Jellyfin container to list VFS entries
        proc = await asyncio.create_subprocess_exec(
            "ssh", "root@10.0.2.10",
            f"pct exec 220 -- docker exec jellyfin ls '{vfs_path}' 2>/dev/null",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            # VFS directory doesn't exist or is empty
            logger.debug(f"VFS directory check failed for {request.title}: {stderr.decode()}")
            return False

        entries = stdout.decode().strip().split('\n')
        entries = [e for e in entries if e]  # Remove empty strings

        # Check if any entry contains part of the title
        # Shokofin uses various title formats, so we do fuzzy matching
        title_lower = request.title.lower()
        title_words = set(title_lower.split())

        for entry in entries:
            entry_lower = entry.lower()
            # Check if significant words from title appear in VFS entry
            matching_words = sum(1 for word in title_words if len(word) > 3 and word in entry_lower)
            if matching_words >= 2 or title_lower in entry_lower:
                logger.debug(f"VFS entry found for {request.title}: {entry}")
                return True

        logger.debug(f"No VFS entry found for {request.title} in {len(entries)} entries")
        return False

    except Exception as e:
        logger.error(f"Error checking VFS entry for {request.title}: {e}")
        return False


async def rebuild_vfs_for_library(media_type: "MediaType") -> bool:
    """Delete VFS folder and trigger library refresh to force rebuild.

    This is the nuclear option when Shokofin's VFS is out of sync.

    Steps:
    1. Delete the VFS folder for the library
    2. Trigger Jellyfin library refresh
    3. Shokofin will recreate VFS from scratch during the scan

    Args:
        media_type: MOVIE or TV to determine which library to rebuild

    Returns:
        True if rebuild was triggered successfully
    """
    from app.models import MediaType

    library_type = "movie" if media_type == MediaType.MOVIE else "tv"
    library_id = SHOKOFIN_VFS_LIBRARIES.get(library_type)

    if not library_id:
        logger.error(f"No VFS library ID configured for type: {library_type}")
        return False

    vfs_path = f"{VFS_BASE_PATH}/{library_id}"

    logger.info(f"[VFS REBUILD] Deleting VFS folder: {vfs_path}")

    try:
        # Step 1: Delete VFS folder
        proc = await asyncio.create_subprocess_exec(
            "ssh", "root@10.0.2.10",
            f"pct exec 220 -- docker exec jellyfin rm -rf '{vfs_path}'",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            logger.error(f"[VFS REBUILD] Failed to delete VFS folder: {stderr.decode()}")
            return False

        logger.info(f"[VFS REBUILD] VFS folder deleted, triggering library refresh...")

        # Step 2: Trigger Jellyfin library refresh
        success = await trigger_jellyfin_library_refresh()

        if success:
            logger.info(f"[VFS REBUILD] Library refresh triggered, waiting for VFS regeneration...")
            # Wait for Shokofin to rebuild VFS
            await asyncio.sleep(VFS_REGENERATION_WAIT_SECONDS)
            logger.info(f"[VFS REBUILD] VFS rebuild complete for {library_type}")
            return True
        else:
            logger.error(f"[VFS REBUILD] Failed to trigger library refresh")
            return False

    except Exception as e:
        logger.error(f"[VFS REBUILD] Error during VFS rebuild: {e}")
        return False


async def trigger_jellyfin_library_refresh() -> bool:
    """Trigger Jellyfin library refresh via API.

    Returns:
        True if refresh was triggered successfully
    """
    if not settings.JELLYFIN_URL or not settings.JELLYFIN_API_KEY:
        logger.error("Jellyfin URL or API key not configured")
        return False

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{settings.JELLYFIN_URL}/Library/Refresh",
                headers={"X-Emby-Token": settings.JELLYFIN_API_KEY},
                timeout=30.0,
            )

            if resp.status_code in (200, 204):
                logger.debug("Jellyfin library refresh triggered successfully")
                return True
            else:
                logger.error(f"Jellyfin library refresh failed: HTTP {resp.status_code}")
                return False

    except Exception as e:
        logger.error(f"Error triggering Jellyfin library refresh: {e}")
        return False


def should_attempt_vfs_rebuild(request: "MediaRequest", stuck_minutes: int = 3) -> bool:
    """Check if we should attempt VFS rebuild for this request.

    Conditions:
    1. Request is anime (non-anime doesn't use Shokofin)
    2. Request is stuck in ANIME_MATCHING for > stuck_minutes
    3. Haven't attempted rebuild in last VFS_REBUILD_COOLDOWN_MINUTES

    Args:
        request: The MediaRequest to check
        stuck_minutes: Minutes stuck before considering rebuild

    Returns:
        True if we should attempt VFS rebuild
    """
    from app.models import RequestState

    # Must be anime
    if not request.is_anime:
        return False

    # Must be in ANIME_MATCHING state
    if request.state != RequestState.ANIME_MATCHING:
        return False

    # Check how long stuck
    now = datetime.utcnow()
    stuck_since = request.state_changed_at or request.updated_at
    stuck_duration = now - stuck_since

    if stuck_duration < timedelta(minutes=stuck_minutes):
        return False

    # Check rebuild cooldown
    if request.vfs_rebuild_at:
        cooldown_elapsed = now - request.vfs_rebuild_at
        if cooldown_elapsed < timedelta(minutes=VFS_REBUILD_COOLDOWN_MINUTES):
            logger.debug(
                f"VFS rebuild on cooldown for {request.title} "
                f"({cooldown_elapsed.total_seconds() / 60:.1f} min since last attempt)"
            )
            return False

    return True
