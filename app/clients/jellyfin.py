"""Jellyfin API client for deletion and user validation."""

import logging
from typing import Optional
from dataclasses import dataclass

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


@dataclass
class JellyfinUser:
    """Jellyfin user info."""
    user_id: str
    username: str
    is_admin: bool


@dataclass
class AuthResult:
    """Result of Jellyfin authentication."""
    success: bool
    token: Optional[str] = None
    user: Optional[JellyfinUser] = None
    error: Optional[str] = None


class JellyfinClient:
    """
    Async client for Jellyfin API.

    Used for:
    - Validating user tokens (auth)
    - Checking admin status
    - Deleting library items
    - Getting user info
    """

    def __init__(self):
        self.base_url = settings.jellyfin_base_url
        self.api_key = settings.JELLYFIN_API_KEY
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
                headers={
                    "X-Emby-Token": self.api_key,
                    "Content-Type": "application/json",
                }
            )
        return self._client

    async def close(self):
        """Close the HTTP client."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None

    async def validate_token(self, token: str) -> Optional[JellyfinUser]:
        """
        Validate a Jellyfin token and return user info.

        Args:
            token: Jellyfin access token from client

        Returns:
            JellyfinUser if valid, None if invalid
        """
        try:
            client = await self._get_client()
            # Use the user's token to get their session info
            response = await client.get(
                "/Sessions",
                headers={"X-Emby-Token": token}
            )

            if response.status_code != 200:
                logger.warning(f"Token validation failed: {response.status_code}")
                return None

            sessions = response.json()
            if not sessions:
                logger.warning("No active sessions found for token")
                return None

            # First session should be the current one
            session = sessions[0]
            user_id = session.get("UserId", "")
            username = session.get("UserName", "")

            # Check if user is admin
            is_admin = user_id in settings.admin_user_ids_list

            return JellyfinUser(
                user_id=user_id,
                username=username,
                is_admin=is_admin
            )

        except httpx.RequestError as e:
            logger.error(f"Request error validating token: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error validating token: {e}")
            return None

    async def get_user_by_id(self, user_id: str) -> Optional[JellyfinUser]:
        """
        Get user info by Jellyfin user ID.

        Args:
            user_id: Jellyfin user ID

        Returns:
            JellyfinUser if found, None otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/Users/{user_id}")

            if response.status_code != 200:
                logger.warning(f"User lookup failed for {user_id}: {response.status_code}")
                return None

            user_data = response.json()
            return JellyfinUser(
                user_id=user_data.get("Id", ""),
                username=user_data.get("Name", ""),
                is_admin=user_id in settings.admin_user_ids_list
            )

        except httpx.RequestError as e:
            logger.error(f"Request error getting user: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error getting user: {e}")
            return None

    async def delete_item(self, item_id: str) -> tuple[bool, str]:
        """
        Handle Jellyfin item removal by triggering a library scan.

        Instead of deleting via API (which has permission issues), we trigger
        a library scan. Jellyfin will automatically remove entries for files
        that no longer exist on disk (deleted by Radarr/Sonarr).

        Args:
            item_id: Jellyfin item ID (used for logging)

        Returns:
            Tuple of (success, message)
        """
        try:
            client = await self._get_client()

            # Trigger library scan - Jellyfin will detect missing files
            response = await client.post("/Library/Refresh")

            if response.status_code in (200, 204):
                logger.info(f"Triggered Jellyfin library scan (item {item_id} will be removed if files missing)")
                return True, "Library scan triggered - item will be removed automatically"
            else:
                # Even if scan trigger fails, files are already deleted
                # Jellyfin will eventually detect this on scheduled scan
                logger.warning(f"Library scan trigger returned {response.status_code}, but files already deleted")
                return True, f"Files deleted - Jellyfin will sync on next scheduled scan"

        except httpx.RequestError as e:
            # Network error, but files are already deleted by Radarr/Sonarr
            logger.warning(f"Could not trigger Jellyfin scan: {e}")
            return True, "Files deleted - Jellyfin will sync on next scheduled scan"
        except Exception as e:
            logger.warning(f"Jellyfin scan trigger error: {e}")
            return True, "Files deleted - Jellyfin will sync on next scheduled scan"

    async def get_item(self, item_id: str) -> Optional[dict]:
        """
        Get a library item by ID (for verification).

        Args:
            item_id: Jellyfin item ID

        Returns:
            Item data dict if found, None if not found
        """
        try:
            client = await self._get_client()
            response = await client.get(f"/Items/{item_id}")

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return None
            else:
                logger.warning(f"Unexpected status getting item {item_id}: {response.status_code}")
                return None

        except Exception as e:
            logger.error(f"Error getting Jellyfin item: {e}")
            return None

    async def health_check(self) -> bool:
        """Check if Jellyfin is reachable."""
        try:
            client = await self._get_client()
            response = await client.get("/System/Info/Public")
            return response.status_code == 200
        except Exception as e:
            logger.error(f"Jellyfin health check failed: {e}")
            return False

    async def trigger_library_scan(self) -> bool:
        """
        Trigger a full library scan in Jellyfin.

        This ensures the library is up-to-date before syncing.
        The scan runs asynchronously in Jellyfin.

        Returns:
            True if scan was triggered successfully
        """
        try:
            client = await self._get_client()
            response = await client.post("/Library/Refresh")

            if response.status_code in (200, 204):
                logger.info("Jellyfin library scan triggered")
                return True
            else:
                logger.warning(f"Jellyfin library scan returned {response.status_code}")
                return False

        except httpx.RequestError as e:
            logger.warning(f"Could not trigger Jellyfin scan: {e}")
            return False
        except Exception as e:
            logger.warning(f"Jellyfin scan trigger error: {e}")
            return False

    async def find_item_by_tmdb(
        self,
        tmdb_id: int,
        media_type: str = "Movie",
    ) -> Optional[dict]:
        """
        Find a single PLAYABLE Jellyfin item by TMDB ID.

        Uses AnyProviderIdEquals filter for O(1) lookup efficiency
        instead of fetching all items and filtering.

        IMPORTANT: Only returns items that have actual media sources (playable).
        Jellyfin can have metadata-only items (e.g., from Jellyseerr sync) that
        have TMDB IDs but no actual video files. We filter these out.

        Args:
            tmdb_id: The TMDB ID to search for
            media_type: Item type ("Movie" or "Series")

        Returns:
            Jellyfin item dict if found AND playable, None otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get(
                "/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": media_type,
                    "AnyProviderIdEquals": f"Tmdb.{tmdb_id}",
                    # Request MediaSources and Path to verify item is playable
                    "Fields": "ProviderIds,MediaSources,Path",
                    # No Limit - AnyProviderIdEquals is broken and returns wrong items,
                    # so we need all candidates to filter by exact TMDB match
                }
            )

            if response.status_code != 200:
                logger.warning(f"Failed to search Jellyfin by TMDB {tmdb_id}: {response.status_code}")
                return None

            data = response.json()
            items = data.get("Items", [])

            if items:
                # CRITICAL: AnyProviderIdEquals filter is broken in Jellyfin -
                # it returns unrelated items. We must verify exact TMDB match.
                exact_match = next(
                    (item for item in items
                     if item.get("ProviderIds", {}).get("Tmdb") == str(tmdb_id)),
                    None
                )

                if not exact_match:
                    logger.debug(
                        f"[JELLYFIN] AnyProviderIdEquals returned {len(items)} items for TMDB {tmdb_id}, "
                        f"but none matched exactly."
                    )
                    return None

                item = exact_match
                item_id = item.get("Id")
                item_name = item.get("Name", "Unknown")

                # Verify item has actual media (not just metadata)
                media_sources = item.get("MediaSources", [])
                path = item.get("Path")

                if media_sources or path:
                    logger.debug(
                        f"Found playable Jellyfin item for TMDB {tmdb_id}: "
                        f"{item_name} ({item_id})"
                    )
                    return item
                else:
                    logger.debug(
                        f"[JELLYFIN] Item {item_name} has TMDB {tmdb_id} but no MediaSources/Path - not playable"
                    )
                    return None

            return None

        except httpx.RequestError as e:
            logger.warning(f"Request error searching Jellyfin by TMDB: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error searching Jellyfin by TMDB: {e}")
            return None

    async def find_item_by_tvdb(
        self,
        tvdb_id: int,
        media_type: str = "Series",
    ) -> Optional[dict]:
        """
        Find a single PLAYABLE Jellyfin item by TVDB ID.

        Uses AnyProviderIdEquals filter for O(1) lookup efficiency.

        Args:
            tvdb_id: The TVDB ID to search for
            media_type: Item type (usually "Series" for TV)

        Returns:
            Jellyfin item dict if found AND playable, None otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get(
                "/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": media_type,
                    "AnyProviderIdEquals": f"Tvdb.{tvdb_id}",
                    "Fields": "ProviderIds,MediaSources,Path",
                }
            )

            if response.status_code != 200:
                logger.warning(f"Failed to search Jellyfin by TVDB {tvdb_id}: {response.status_code}")
                return None

            data = response.json()
            items = data.get("Items", [])

            if items:
                # Verify exact TVDB match (same issue as TMDB - filter is unreliable)
                exact_match = next(
                    (item for item in items
                     if item.get("ProviderIds", {}).get("Tvdb") == str(tvdb_id)),
                    None
                )

                if not exact_match:
                    logger.debug(
                        f"[JELLYFIN] AnyProviderIdEquals returned {len(items)} items for TVDB {tvdb_id}, "
                        f"but none matched exactly."
                    )
                    return None

                item = exact_match
                item_id = item.get("Id")
                item_name = item.get("Name", "Unknown")

                # Verify item has actual media (not just metadata)
                media_sources = item.get("MediaSources", [])
                path = item.get("Path")

                if media_sources or path:
                    logger.debug(
                        f"Found playable Jellyfin item for TVDB {tvdb_id}: "
                        f"{item_name} ({item_id})"
                    )
                    return item
                else:
                    logger.debug(
                        f"[JELLYFIN] Item {item_name} has TVDB {tvdb_id} but no MediaSources/Path - not playable"
                    )
                    return None

            return None

        except httpx.RequestError as e:
            logger.warning(f"Request error searching Jellyfin by TVDB: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error searching Jellyfin by TVDB: {e}")
            return None

    async def search_by_title(
        self,
        title: str,
        year: Optional[int] = None,
    ) -> Optional[dict]:
        """
        Search Jellyfin by title (fallback when provider IDs don't match).

        Used for anime that may be recategorized by Shoko.

        Args:
            title: The media title to search for
            year: Optional year for more precise matching

        Returns:
            Jellyfin item dict if found AND playable, None otherwise
        """
        try:
            client = await self._get_client()
            response = await client.get(
                "/Items",
                params={
                    "Recursive": "true",
                    "SearchTerm": title,
                    "IncludeItemTypes": "Movie,Series",
                    "Fields": "ProviderIds,MediaSources,Path,ProductionYear",
                    "Limit": 10,
                }
            )

            if response.status_code != 200:
                logger.warning(f"Failed to search Jellyfin by title '{title}': {response.status_code}")
                return None

            data = response.json()
            items = data.get("Items", [])

            for item in items:
                item_name = item.get("Name", "")
                item_year = item.get("ProductionYear")

                # Check if title matches (case-insensitive)
                if item_name.lower() != title.lower():
                    continue

                # If year provided, check it matches
                if year and item_year and item_year != year:
                    continue

                # Verify item is playable
                media_sources = item.get("MediaSources", [])
                path = item.get("Path")

                if media_sources or path:
                    logger.debug(
                        f"Found playable Jellyfin item by title search: "
                        f"'{item_name}' (ID: {item.get('Id')})"
                    )
                    return item

            logger.debug(f"No playable item found for title '{title}'" + (f" ({year})" if year else ""))
            return None

        except httpx.RequestError as e:
            logger.warning(f"Request error searching Jellyfin by title: {e}")
            return None
        except Exception as e:
            logger.warning(f"Error searching Jellyfin by title: {e}")
            return None

    async def get_all_items(
        self,
        include_types: list[str] | None = None,
        fields: list[str] | None = None,
    ) -> list[dict]:
        """
        Fetch all library items with provider IDs for bulk sync.

        Args:
            include_types: Item types to include (default: Movie, Series)
            fields: Additional fields to fetch (default: ProviderIds, Path, Overview)

        Returns:
            List of Jellyfin items with metadata
        """
        if include_types is None:
            include_types = ["Movie", "Series"]
        if fields is None:
            fields = ["ProviderIds", "Path", "Overview", "PremiereDate", "ProductionYear"]

        try:
            client = await self._get_client()
            response = await client.get(
                "/Items",
                params={
                    "Recursive": "true",
                    "IncludeItemTypes": ",".join(include_types),
                    "Fields": ",".join(fields),
                }
            )

            if response.status_code != 200:
                logger.error(f"Failed to fetch Jellyfin items: {response.status_code}")
                return []

            data = response.json()
            items = data.get("Items", [])
            logger.info(f"Fetched {len(items)} items from Jellyfin")
            return items

        except httpx.RequestError as e:
            logger.error(f"Request error fetching Jellyfin items: {e}")
            return []
        except Exception as e:
            logger.error(f"Unexpected error fetching Jellyfin items: {e}")
            return []

    async def authenticate(self, username: str, password: str) -> AuthResult:
        """
        Authenticate a user with Jellyfin.

        Args:
            username: Jellyfin username
            password: Jellyfin password

        Returns:
            AuthResult with token and user info if successful
        """
        try:
            # Create a fresh client without the API key for user auth
            async with httpx.AsyncClient(
                base_url=self.base_url,
                timeout=30.0,
            ) as client:
                # Jellyfin requires specific authorization header format
                auth_header = (
                    'MediaBrowser Client="Status Tracker", '
                    'Device="Web", '
                    'DeviceId="status-tracker-web", '
                    'Version="1.0.0"'
                )

                response = await client.post(
                    "/Users/AuthenticateByName",
                    headers={
                        "X-Emby-Authorization": auth_header,
                        "Content-Type": "application/json",
                    },
                    json={
                        "Username": username,
                        "Pw": password,
                    }
                )

                if response.status_code == 200:
                    data = response.json()
                    user_id = data.get("User", {}).get("Id", "")
                    user_name = data.get("User", {}).get("Name", "")
                    access_token = data.get("AccessToken", "")

                    if not access_token:
                        return AuthResult(
                            success=False,
                            error="No access token in response"
                        )

                    user = JellyfinUser(
                        user_id=user_id,
                        username=user_name,
                        is_admin=user_id in settings.admin_user_ids_list
                    )

                    logger.info(f"User {user_name} authenticated successfully")
                    return AuthResult(
                        success=True,
                        token=access_token,
                        user=user
                    )

                elif response.status_code == 401:
                    return AuthResult(
                        success=False,
                        error="Invalid username or password"
                    )
                else:
                    return AuthResult(
                        success=False,
                        error=f"Authentication failed: {response.status_code}"
                    )

        except httpx.RequestError as e:
            logger.error(f"Request error during authentication: {e}")
            return AuthResult(
                success=False,
                error=f"Connection error: {e}"
            )
        except Exception as e:
            logger.error(f"Unexpected error during authentication: {e}")
            return AuthResult(
                success=False,
                error=f"Unexpected error: {e}"
            )


# Singleton instance
jellyfin_client = JellyfinClient()
