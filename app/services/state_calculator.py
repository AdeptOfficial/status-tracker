"""State Calculator - Derive request state from episode states.

For TV shows, the request's state is an aggregate of individual episode states.
This module provides the calculation logic for that aggregation.

Examples:
- All episodes AVAILABLE → request AVAILABLE
- Any episode FAILED → request FAILED
- Mixed in-progress states → highest priority in-progress state
"""

from typing import TYPE_CHECKING

from app.models import MediaType, RequestState, EpisodeState

if TYPE_CHECKING:
    from app.models import MediaRequest


def calculate_aggregate_state(request: "MediaRequest") -> RequestState:
    """
    Derive request state from episode states for TV shows.

    For movies, returns the current state unchanged.

    Priority rules:
    1. All AVAILABLE → AVAILABLE
    2. Any FAILED → FAILED
    3. Otherwise → highest priority in-progress state

    State priority (highest to lowest):
    - ANIME_MATCHING (waiting for Shoko)
    - IMPORTING (waiting for Jellyfin)
    - DOWNLOADED (downloaded, waiting for import)
    - DOWNLOADING (actively downloading)
    - GRABBING (grab sent to download client)

    Args:
        request: MediaRequest with episodes relationship loaded

    Returns:
        Calculated RequestState based on episode states
    """
    # Movies don't have episodes - return current state
    if request.media_type == MediaType.MOVIE:
        return request.state

    # TV shows without episodes yet - return current state
    episodes = request.episodes
    if not episodes:
        return request.state

    states = [ep.state for ep in episodes]

    # Rule 1: All episodes available → request available
    if all(s == EpisodeState.AVAILABLE for s in states):
        return RequestState.AVAILABLE

    # Rule 2: Any episode failed → request failed
    if any(s == EpisodeState.FAILED for s in states):
        return RequestState.FAILED

    # Rule 3: Return highest priority in-progress state
    # Priority order from highest to lowest
    state_priority = [
        (EpisodeState.ANIME_MATCHING, RequestState.ANIME_MATCHING),
        (EpisodeState.IMPORTING, RequestState.IMPORTING),
        (EpisodeState.DOWNLOADED, RequestState.DOWNLOADED),
        (EpisodeState.DOWNLOADING, RequestState.DOWNLOADING),
        (EpisodeState.GRABBING, RequestState.GRABBING),
    ]

    for ep_state, req_state in state_priority:
        if any(s == ep_state for s in states):
            return req_state

    # Fallback - shouldn't happen if states are valid
    return request.state


def get_episode_progress(request: "MediaRequest") -> tuple[int, int]:
    """
    Get episode completion progress.

    Args:
        request: MediaRequest with episodes relationship loaded

    Returns:
        Tuple of (completed_count, total_count)
    """
    if request.media_type == MediaType.MOVIE:
        # Movies don't have episodes - return 0/0 or 1/1 based on state
        if request.state == RequestState.AVAILABLE:
            return (1, 1)
        return (0, 1)

    episodes = request.episodes
    if not episodes:
        return (0, 0)

    completed = sum(1 for ep in episodes if ep.state == EpisodeState.AVAILABLE)
    return (completed, len(episodes))
