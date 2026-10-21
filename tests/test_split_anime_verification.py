"""A sequel must never become Ready using the original season's files."""
from unittest.mock import AsyncMock
import httpx
import pytest
from app.models import MediaRequest, MediaType, RequestState, Episode, EpisodeState
from app.services import jellyfin_verifier as verifier
from app.clients.shoko import shoko_http_client
from app.clients.jellyfin import JellyfinClient

async def setup(db, monkeypatch, found):
    monkeypatch.setattr(verifier.settings, "ENABLE_SHOKO", True)
    r = MediaRequest(title="Same provider show", media_type=MediaType.TV,
                     state=RequestState.ANIME_MATCHING, is_anime=True,
                     tvdb_id=456, tmdb_id=123, season=2, total_episodes=2,
                     jellyfin_id="original-show")
    r.episodes = [Episode(season_number=2, episode_number=n,
                         state=EpisodeState.ANIME_MATCHING,
                         final_path=f"/anime/show/Season 2/episode{n}.mkv") for n in [1, 2]]
    db.add(r); await db.commit()
    monkeypatch.setattr(shoko_http_client, "confirmed_file_for_path", AsyncMock(side_effect=[101, 102]))
    monkeypatch.setattr(verifier.jellyfin_client, "find_episodes_by_shoko_files", AsyncMock(return_value=found))
    monkeypatch.setattr(verifier.jellyfin_client, "find_item_by_tvdb", AsyncMock(side_effect=AssertionError("Do not guess from shared series ID")))
    monkeypatch.setattr(verifier.broadcaster, "broadcast_update", AsyncMock())
    return r

def entry(file_id, episode_id, series="sequel-show", path="/vfs/video.mkv"):
    return {"Id": episode_id, "SeriesId": series, "ParentIndexNumber": 1,
            "IndexNumber": file_id - 100, "Path": path,
            "ProviderIds": {"Shoko File": str(file_id), "Tvdb": "same-incorrect-provider"}}

@pytest.mark.asyncio
async def test_split_sequel_uses_files_despite_wrong_provider_and_season(db_session, monkeypatch):
    r = await setup(db_session, monkeypatch, [entry(101, "a"), entry(102, "b")])
    assert await verifier.verify_request(r, db_session)
    assert r.jellyfin_id == "sequel-show" and r.state == RequestState.AVAILABLE
    assert [(e.season_number, e.jellyfin_id) for e in r.episodes] == [(2, "a"), (2, "b")]

@pytest.mark.asyncio
@pytest.mark.parametrize("found", [None, [], [entry(1, "original-1"), entry(2, "original-2")],
    [entry(101, "a"), entry(101, "duplicate"), entry(102, "b")],
    [entry(101, "a"), entry(102, "b", series="other-show")],
    [entry(101, "a", path=None), entry(102, "b", path=None)]])
async def test_missing_wrong_ambiguous_or_unplayable_files_never_complete(db_session, monkeypatch, found):
    r = await setup(db_session, monkeypatch, found)
    assert not await verifier.verify_request(r, db_session)
    assert r.state == RequestState.ANIME_MATCHING
    assert all(e.state != EpisodeState.AVAILABLE for e in r.episodes)

@pytest.mark.asyncio
async def test_partial_exact_files_do_not_complete_whole_season(db_session, monkeypatch):
    r = await setup(db_session, monkeypatch, [entry(101, "a")])
    assert not await verifier.verify_request(r, db_session)
    assert r.episodes[0].state == EpisodeState.AVAILABLE
    assert r.episodes[1].state == EpisodeState.ANIME_MATCHING
    assert r.state == RequestState.ANIME_MATCHING

@pytest.mark.asyncio
async def test_unmatched_or_shared_import_file_never_guesses_episode(db_session, monkeypatch):
    r = await setup(db_session, monkeypatch, [])
    for ids in [[None], [101, 101]]:
        monkeypatch.setattr(shoko_http_client, "confirmed_file_for_path", AsyncMock(side_effect=ids))
        assert not await verifier.verify_request(r, db_session)
    verifier.jellyfin_client.find_episodes_by_shoko_files.assert_not_awaited()

@pytest.mark.asyncio
async def test_file_inventory_paginates_and_requests_provider_evidence():
    paths=[]
    def reply(req):
        paths.append(int(req.url.params["StartIndex"]))
        assert "ProviderIds" in req.url.params["Fields"]
        i = 101 if paths[-1] == 0 else 102
        return httpx.Response(200, json={"Items": [entry(i, str(i))], "TotalRecordCount": 201})
    c=JellyfinClient(); c._client=httpx.AsyncClient(base_url="http://synthetic",transport=httpx.MockTransport(reply))
    try:
        result=await c.find_episodes_by_shoko_files({101,102})
        assert paths == [0,200] and len(result)==2
    finally: await c.close()

@pytest.mark.asyncio
@pytest.mark.parametrize("status,data", [(500,{}),(200,{"Items":[]}),(200,{"Items":[],"TotalRecordCount":201})])
async def test_failed_or_incomplete_inventory_is_not_absence(status,data):
    c=JellyfinClient(); c._client=httpx.AsyncClient(base_url="http://synthetic",transport=httpx.MockTransport(lambda req:httpx.Response(status,json=data)))
    try: assert await c.find_episodes_by_shoko_files({101}) is None
    finally: await c.close()

@pytest.mark.asyncio
async def test_previously_ready_episode_still_needs_current_file_evidence(db_session, monkeypatch):
    r = await setup(db_session, monkeypatch, [entry(102, "b")])
    r.episodes[0].state = EpisodeState.AVAILABLE
    assert not await verifier.verify_request(r, db_session)
    assert r.state == RequestState.ANIME_MATCHING
