"""Shoko auto-linker service.

Attempts to automatically link files that Shoko couldn't hash-match
by searching for the anime by title and linking to episode 1 (for movies)
or the appropriate episode (for TV).

WHY: When files don't have ED2K hashes in AniDB (personal rips, rare encodes),
Shoko sends FileNotMatched. Instead of requiring manual intervention, this
service attempts to auto-link by searching Shoko's local database.

ALTERNATIVES CONSIDERED:
- Manual-only linking: Requires user to use Shoko GUI (poor UX)
- Pre-linking at import: Not possible since Shoko processes async

ASSUMPTIONS:
- Series is already in Shoko's database (user has at least one file from that series)
- Title matching is fuzzy enough to find the series
- Movies always link to episode 1
"""

import json
import logging
import re
from typing import Optional, TYPE_CHECKING

from app.clients.shoko import shoko_http_client
from app.models import MediaRequest, MediaType

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from app.models import Episode

logger = logging.getLogger(__name__)


async def attempt_auto_link(
    request: MediaRequest,
    file_id: int,
    db: "AsyncSession",
) -> tuple[bool, str]:
    """
    Attempt to auto-link an unmatched file to its anime.

    Strategy:
    1. Search Shoko's local series by request title
    2. Try alternate titles if primary fails
    3. If series found, link file to episode 1 (movies) or appropriate episode (TV)

    Returns:
        Tuple of (success, message)
    """
    titles_to_try = [request.title]

    # Add alternate titles if available
    if request.alternate_titles:
        try:
            alt_titles = json.loads(request.alternate_titles)
            if isinstance(alt_titles, list):
                titles_to_try.extend(alt_titles)
        except (json.JSONDecodeError, TypeError):
            pass

    # Try each title
    for title in titles_to_try:
        logger.info(f"[AUTO-LINK] Searching Shoko for: '{title}'")

        series_list = await shoko_http_client.search_series(title, fuzzy=True)

        if not series_list:
            continue

        # Take first match but VERIFY it's actually related to our title
        series = series_list[0]
        series_id = series.get("IDs", {}).get("ID") or series.get("ID")
        series_name = series.get("Name", "Unknown")

        if not series_id:
            logger.warning(f"[AUTO-LINK] Series found but no ID: {series}")
            continue

        # Verify the series name has some overlap with search title
        # This prevents linking "Your Name" to "Akira" due to loose fuzzy matching
        title_lower = title.lower()
        series_name_lower = series_name.lower()

        # Check if any significant word (3+ chars) from the title appears in series name
        title_words = [w for w in title_lower.replace(".", " ").split() if len(w) >= 3]
        has_overlap = any(word in series_name_lower for word in title_words)

        # Also check reverse - series name words in title
        series_words = [w for w in series_name_lower.replace(".", " ").split() if len(w) >= 3]
        has_reverse_overlap = any(word in title_lower for word in series_words)

        if not has_overlap and not has_reverse_overlap:
            logger.warning(f"[AUTO-LINK] Series '{series_name}' doesn't match title '{title}', skipping")
            continue

        logger.info(f"[AUTO-LINK] Found series: {series_name} (ID: {series_id})")

        # For movies, link to episode 1
        if request.media_type == MediaType.MOVIE:
            success, msg = await shoko_http_client.link_file_from_series(
                file_id=file_id,
                series_id=series_id,
                range_start="1",
                range_end="1",
            )
        else:
            # For TV, extract episode number from Episode record or filename
            episode_num = await _get_episode_number_for_file(file_id, request, db)
            if episode_num:
                success, msg = await shoko_http_client.link_file_from_series(
                    file_id=file_id,
                    series_id=series_id,
                    range_start=str(episode_num),
                    range_end=str(episode_num),
                )
            else:
                # Can't determine episode number - need manual intervention
                return False, f"Found series '{series_name}' but couldn't determine episode number"

        if success:
            logger.info(f"[AUTO-LINK] Successfully linked file {file_id} to {series_name}")
            return True, f"Auto-linked to '{series_name}'"
        else:
            logger.warning(f"[AUTO-LINK] Link failed: {msg}")

    # All titles exhausted
    return False, f"Could not find matching series in Shoko for any of: {titles_to_try}"


async def _get_episode_number_for_file(
    file_id: int,
    request: MediaRequest,
    db: "AsyncSession"
) -> Optional[int]:
    """
    Determine episode number for a TV file.

    Strategy:
    1. Look up Episode record by file path (most reliable)
    2. Parse episode number from filename as fallback (S01E06 pattern)
    """
    from sqlalchemy import select
    from app.models import Episode

    # Get file info from Shoko to get the path
    file_info = await shoko_http_client.get_file_info(file_id)
    if not file_info:
        return None

    # Try to find matching Episode record by path
    locations = file_info.get("Locations", [])
    relative_path = locations[0].get("RelativePath", "") if locations else ""

    if relative_path:
        filename = relative_path.split("/")[-1]
        stmt = select(Episode).where(
            Episode.request_id == request.id,
            Episode.final_path.endswith(filename)
        )
        result = await db.execute(stmt)
        episode = result.scalar_one_or_none()
        if episode:
            return episode.episode_number

    # Fallback: parse from filename (e.g., "S01E06" or "- 06")
    filename = relative_path.split("/")[-1] if relative_path else ""

    # Try S01E06 format
    match = re.search(r'[Ss](\d+)[Ee](\d+)', filename)
    if match:
        return int(match.group(2))

    # Try " - 06" format (common for anime)
    match = re.search(r' - (\d+)', filename)
    if match:
        return int(match.group(1))

    return None


async def attempt_episode_auto_link(
    request: MediaRequest,
    episode: "Episode",
    file_id: int,
    db: "AsyncSession",
) -> tuple[bool, str]:
    """
    Attempt to auto-link an unmatched TV episode file.

    Uses the episode number from the Episode record.
    """
    titles_to_try = [request.title]

    # Add alternate titles
    if request.alternate_titles:
        try:
            alt_titles = json.loads(request.alternate_titles)
            if isinstance(alt_titles, list):
                titles_to_try.extend(alt_titles)
        except (json.JSONDecodeError, TypeError):
            pass

    episode_num = episode.episode_number

    for title in titles_to_try:
        logger.info(f"[AUTO-LINK] Searching Shoko for TV series: '{title}'")

        series_list = await shoko_http_client.search_series(title, fuzzy=True)
        if not series_list:
            continue

        series = series_list[0]
        series_id = series.get("IDs", {}).get("ID") or series.get("ID")
        series_name = series.get("Name", "Unknown")

        if not series_id:
            continue

        # Verify series name matches to prevent wrong linking
        title_lower = title.lower()
        series_name_lower = series_name.lower()
        title_words = [w for w in title_lower.replace(".", " ").split() if len(w) >= 3]
        has_overlap = any(word in series_name_lower for word in title_words)
        series_words = [w for w in series_name_lower.replace(".", " ").split() if len(w) >= 3]
        has_reverse_overlap = any(word in title_lower for word in series_words)

        if not has_overlap and not has_reverse_overlap:
            logger.warning(f"[AUTO-LINK] Series '{series_name}' doesn't match title '{title}', skipping")
            continue

        logger.info(f"[AUTO-LINK] Found series: {series_name}, linking episode {episode_num}")

        success, msg = await shoko_http_client.link_file_from_series(
            file_id=file_id,
            series_id=series_id,
            range_start=str(episode_num),
            range_end=str(episode_num),
        )

        if success:
            return True, f"Auto-linked to '{series_name}' episode {episode_num}"

    return False, f"Could not find series for: {titles_to_try}"
