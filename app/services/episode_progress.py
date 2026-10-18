"""Conservative episode-file matching and display-only progress summaries."""
import math
import re
from pathlib import PurePosixPath

from app.services.state_calculator import season_episodes

COMPLETE = {'downloaded', 'importing', 'anime_matching', 'match_failed', 'available'}
VIDEO = {'.mkv', '.mp4', '.avi', '.m4v', '.ts', '.webm'}
MARKER = re.compile(r'(?i)(?<![a-z0-9])s(\d{1,3})e(\d{1,4})(?!\d)')


def valid_progress(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= 1 else None


def file_progress(episodes, files):
    """Return observed fractions keyed by (season, episode), never guess packs."""
    keys = {(e.season_number, e.episode_number) for e in episodes}
    candidates = {}
    videos = []
    for f in files:
        name = PurePosixPath(str(f.get('name', '')).replace('\\', '/')).name
        if PurePosixPath(name).suffix.lower() not in VIDEO:
            continue
        videos.append(f)
        matches = list(MARKER.finditer(name))
        if len(matches) != 1:
            continue
        match = matches[0]
        # Combined episodes/ranges are intentionally unsupported.
        if re.match(r'(?i)(?:e\d|[-_ ]+(?:e|s\d+e)?\d)', name[match.end():]):
            continue
        key = tuple(map(int, match.groups()))
        if key in keys:
            candidates.setdefault(key, []).append(f)
    if not candidates and len(keys) == 1 and len(videos) == 1:
        name = str(videos[0].get('name', ''))
        # Do not override explicit conflicting or multi-episode identification.
        if not MARKER.search(name):
            candidates[next(iter(keys))] = videos
    result = {}
    for key, rows in candidates.items():
        if len(rows) == 1 and rows[0].get('priority', 1) != 0:
            value = valid_progress(rows[0].get('progress'))
            if value is not None:
                result[key] = value
    return result


def episode_percent(episode):
    progress = valid_progress(getattr(episode, 'download_progress', None))
    # Do not round an incomplete file to 100%.
    return min(99, math.floor(progress * 100 + 1e-9)) if progress is not None and progress < 1 else (100 if progress == 1 else None)


def episode_summary(request):
    episodes = season_episodes(request)
    ready = sum(ep.state.value == 'available' for ep in episodes)
    downloaded = sum(ep.state.value in COMPLETE or (
        ep.state.value == 'downloading' and valid_progress(getattr(ep, 'download_progress', None)) == 1
    ) for ep in episodes)
    return {'downloaded': downloaded, 'ready': ready,
            'total': max(request.total_episodes or 0, len(episodes))}
