"""season_episodes(): display counting must be scoped to the request's season.

Regression for the prod "47/22 ready" card: an S02 request (total_episodes=22)
carried 47 episode rows across S01+S02 because whole-series webhooks were
correlated to a single-season request.
"""

from types import SimpleNamespace

from app.services.state_calculator import season_episodes


def _ep(season, number):
    return SimpleNamespace(season_number=season, episode_number=number)


def test_scopes_to_request_season():
    request = SimpleNamespace(
        season=2,
        episodes=[_ep(1, i) for i in range(1, 23)] + [_ep(2, i) for i in range(1, 26)],
    )
    eps = season_episodes(request)
    assert len(eps) == 25
    assert all(ep.season_number == 2 for ep in eps)


def test_no_season_returns_all():
    request = SimpleNamespace(season=None, episodes=[_ep(1, 1), _ep(2, 1)])
    assert len(season_episodes(request)) == 2


def test_falls_back_when_nothing_matches():
    # Season numbering mismatch: better to show the old behavior than nothing
    request = SimpleNamespace(season=3, episodes=[_ep(1, 1), _ep(1, 2)])
    assert len(season_episodes(request)) == 2


def test_empty_episodes():
    request = SimpleNamespace(season=2, episodes=[])
    assert season_episodes(request) == []
