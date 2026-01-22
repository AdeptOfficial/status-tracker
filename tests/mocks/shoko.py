"""Mock Shoko client for testing anime matching."""

from typing import Optional


class MockShokoClient:
    """
    Mock Shoko SignalR client for testing anime matching.

    Usage:
        mock_shoko = MockShokoClient()
        mock_shoko.add_file_match("/data/anime/movies/Title/file.mkv", series_id=123)
        event = mock_shoko.create_file_matched_event("/data/anime/movies/Title/file.mkv")
    """

    def __init__(self):
        self.file_matches: dict[str, dict] = {}
        self.events: list[dict] = []

    def add_file_match(
        self,
        path: str,
        file_id: int = 1,
        series_id: Optional[int] = None,
        has_cross_refs: bool = True,
        anidb_id: Optional[int] = None,
        anidb_type: str = "Movie",
    ):
        """
        Register a file that Shoko will "match".

        Args:
            path: Full path or relative path to the file
            file_id: Shoko's internal file ID
            series_id: Shoko series ID (if matched to a series)
            has_cross_refs: Whether the file has AniDB cross-references
            anidb_id: AniDB ID for the match
            anidb_type: AniDB type ("Movie", "TVSeries", "TVSpecial", etc.)
        """
        cross_refs = []
        if has_cross_refs and anidb_id:
            cross_refs.append({
                "AniDBID": anidb_id,
                "AniDBType": anidb_type,
            })

        self.file_matches[path] = {
            "FileID": file_id,
            "RelativePath": path.replace("/data/", "") if path.startswith("/data/") else path,
            "CrossReferences": cross_refs,
            "SeriesID": series_id,
        }

    def create_file_matched_event(self, path: str) -> Optional[dict]:
        """
        Create a FileMatched SignalR event for a registered file.

        Returns None if the file wasn't registered with add_file_match.
        """
        match = self.file_matches.get(path)
        if not match:
            # Try matching by relative path
            for registered_path, file_info in self.file_matches.items():
                if path.endswith(file_info["RelativePath"]) or file_info["RelativePath"].endswith(path):
                    match = file_info
                    break

        if not match:
            return None

        event = {
            "EventType": "FileMatched",
            "FileInfo": match,
        }
        self.events.append(event)
        return event

    def create_file_hashed_event(self, path: str, file_id: int = 1) -> dict:
        """Create a FileHashed SignalR event."""
        event = {
            "EventType": "FileHashed",
            "FileInfo": {
                "FileID": file_id,
                "RelativePath": path.replace("/data/", "") if path.startswith("/data/") else path,
            },
        }
        self.events.append(event)
        return event

    def create_series_updated_event(self, series_id: int, name: str = "Test Series") -> dict:
        """Create a SeriesUpdated SignalR event."""
        event = {
            "EventType": "SeriesUpdated",
            "SeriesInfo": {
                "ID": series_id,
                "Name": name,
            },
        }
        self.events.append(event)
        return event

    def get_events(self) -> list[dict]:
        """Get all generated events."""
        return self.events.copy()

    def clear_events(self):
        """Clear event history."""
        self.events = []
