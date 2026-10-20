"""Wire-level deletion regressions model file permissions, stale IDs and API errors."""
import httpx
import pytest
from app.clients.radarr import RadarrClient
from app.clients.jellyfin import JellyfinClient

FOLDER = "/data/movies/Synthetic"
FILE = FOLDER + "/Synthetic.mkv"

@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["success", "file_retained", "file_error", "stale_record", "disk_error", "bad_listing", "identity_changed"])
async def test_radarr_requires_actual_file_absence(mode):
    exists = True
    record = mode != "stale_record"
    calls = []
    def handler(request):
        nonlocal exists, record
        calls.append((request.method, request.url.path))
        if request.url.path == "/api/v3/movie/5" and request.method == "GET":
            return httpx.Response(200, json={"id": 5, "tmdbId": 999 if mode == "identity_changed" else 123, "path": FOLDER, "movieFile": {"id": 17}}) if record else httpx.Response(404)
        if request.url.path == "/api/v3/filesystem":
            assert request.url.params["path"] == FOLDER + "/"
            assert request.url.params["includeFiles"] == "true"
            if mode == "disk_error": return httpx.Response(403)
            if mode == "bad_listing": return httpx.Response(200, json={})
            return httpx.Response(200, json={"files": [{"path": FILE}] if exists else [], "directories": []})
        if request.url.path == "/api/v3/moviefile/17" and request.method == "DELETE":
            if mode == "file_error": return httpx.Response(500)
            if mode != "file_retained": exists = False
            return httpx.Response(200)
        if request.url.path == "/api/v3/movie/5" and request.method == "DELETE":
            assert exists is False
            assert request.url.params["deleteFiles"] == "false"
            record = False
            return httpx.Response(200)
        raise AssertionError(str(request.url))
    client = RadarrClient()
    client._client = httpx.AsyncClient(base_url="http://synthetic", transport=httpx.MockTransport(handler))
    try:
        success, message = await client.delete_movie(5, movie_path=FOLDER, tmdb_id=123)
        assert success is (mode == "success")
        if mode != "success":
            assert ("DELETE", "/api/v3/movie/5") not in calls
            assert exists
    finally: await client.close()

@pytest.mark.asyncio
async def test_stale_record_only_succeeds_with_persisted_empty_directory():
    def handler(request):
        if request.url.path == "/api/v3/movie/5": return httpx.Response(404)
        assert request.url.path == "/api/v3/filesystem"
        return httpx.Response(200, json={"files": [], "directories": []})
    client = RadarrClient()
    client._client = httpx.AsyncClient(base_url="http://synthetic", transport=httpx.MockTransport(handler))
    try:
        assert (await client.delete_movie(5))[0] is False
        assert (await client.delete_movie(5, movie_path=FOLDER))[0] is True
    finally: await client.close()

@pytest.mark.asyncio
@pytest.mark.parametrize("status,items,raises", [(200, [], False), (200, [{"Id": "abc"}], False), (400, None, True), (401, None, True), (500, None, True), (200, [{"Id": "other"}], True)])
async def test_jellyfin_collection_query_has_strict_absence_semantics(status, items, raises):
    def handler(request):
        assert request.url.path == "/Items"
        assert request.url.params["Ids"] == "abc"
        return httpx.Response(status, json={"Items": items})
    client = JellyfinClient()
    client._client = httpx.AsyncClient(base_url="http://synthetic", transport=httpx.MockTransport(handler))
    try:
        if raises:
            with pytest.raises((httpx.HTTPError, ValueError)): await client.get_item("abc")
        else:
            assert await client.get_item("abc") == (items[0] if items else None)
    finally: await client.close()

@pytest.mark.asyncio
@pytest.mark.parametrize("status,data,raises", [(200, {"id": 123}, False), (200, {"id": 123, "mediaInfo": {"id": 4}}, False), (500, {}, True), (200, {"id": 456}, True), (200, {"id": 123, "mediaInfo": {}}, True)])
async def test_jellyseerr_lookup_cannot_hide_errors(status, data, raises):
    from app.clients.jellyseerr import JellyseerrClient
    client = JellyseerrClient()
    client._client = httpx.AsyncClient(base_url="http://synthetic", transport=httpx.MockTransport(lambda req: httpx.Response(status, json=data)))
    try:
        if raises:
            with pytest.raises((httpx.HTTPError, ValueError)): await client.get_media_id_by_tmdb(123, "movie")
        else:
            assert await client.get_media_id_by_tmdb(123, "movie") == (data.get("mediaInfo") or {}).get("id")
    finally: await client.close()
