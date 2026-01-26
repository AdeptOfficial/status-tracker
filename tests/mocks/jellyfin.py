"""Mock Jellyfin client for testing verification."""

from typing import Optional


class MockJellyfinClient:
    """
    Mock Jellyfin client for testing library verification.

    Usage:
        mock_jellyfin = MockJellyfinClient()
        mock_jellyfin.add_item(tmdb_id=533514, item_type="Movie", jellyfin_id="abc123")
        item = await mock_jellyfin.find_item_by_provider_id("Tmdb", 533514, "Movie")
    """

    def __init__(self):
        self.items: list[dict] = []

    def add_item(
        self,
        jellyfin_id: str = "test-item-id",
        name: str = "Test Item",
        item_type: str = "Movie",
        tmdb_id: Optional[int] = None,
        tvdb_id: Optional[int] = None,
        imdb_id: Optional[str] = None,
        path: Optional[str] = None,
        has_media_sources: bool = True,
    ):
        """Add a mock Jellyfin item."""
        provider_ids = {}
        if tmdb_id:
            provider_ids["Tmdb"] = str(tmdb_id)
        if tvdb_id:
            provider_ids["Tvdb"] = str(tvdb_id)
        if imdb_id:
            provider_ids["Imdb"] = imdb_id

        item = {
            "Id": jellyfin_id,
            "Name": name,
            "Type": item_type,
            "ProviderIds": provider_ids,
        }

        if path:
            item["Path"] = path

        if has_media_sources:
            item["MediaSources"] = [{"Id": "source-1", "Path": path or "/test/path"}]

        self.items.append(item)

    def clear(self):
        """Clear all mock items."""
        self.items = []

    async def find_item_by_provider_id(
        self,
        provider: str,
        provider_id: int,
        item_type: Optional[str] = None
    ) -> Optional[dict]:
        """
        Find item by provider ID (Tmdb, Tvdb, Imdb).

        Args:
            provider: Provider name ("Tmdb", "Tvdb", "Imdb")
            provider_id: The ID to search for
            item_type: Optional type filter ("Movie", "Series")
        """
        for item in self.items:
            # Check provider ID matches
            provider_ids = item.get("ProviderIds", {})
            if str(provider_ids.get(provider)) == str(provider_id):
                # Check type if specified
                if item_type and item.get("Type") != item_type:
                    continue
                return item
        return None

    async def search_by_title(
        self,
        title: str,
        year: Optional[int] = None
    ) -> Optional[dict]:
        """Search by title (fuzzy match)."""
        title_lower = title.lower()
        for item in self.items:
            if title_lower in item.get("Name", "").lower():
                return item
        return None

    async def get(self, path: str, params: Optional[dict] = None) -> dict:
        """Mock GET request to Jellyfin API."""
        # Parse the path to determine what's being requested
        if "Items" in path:
            # Filter items based on params
            filtered = self.items.copy()

            if params:
                # Filter by provider ID
                provider_filter = params.get("AnyProviderIdEquals")
                if provider_filter:
                    provider, id_str = provider_filter.split(".", 1)
                    filtered = [
                        item for item in filtered
                        if str(item.get("ProviderIds", {}).get(provider)) == id_str
                    ]

                # Filter by item type
                type_filter = params.get("IncludeItemTypes")
                if type_filter:
                    types = type_filter.split(",")
                    filtered = [
                        item for item in filtered
                        if item.get("Type") in types
                    ]

            return {
                "Items": filtered,
                "TotalRecordCount": len(filtered)
            }

        return {"Items": [], "TotalRecordCount": 0}
