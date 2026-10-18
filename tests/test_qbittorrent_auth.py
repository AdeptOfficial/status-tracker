"""Authentication works with credentials and existing server-authorized access."""
import httpx
import pytest
from app.clients.qbittorrent import QBittorrentClient

@pytest.mark.asyncio
@pytest.mark.parametrize('version', ['v5.2.4', 'v4.6.7', '5.0.0beta1'])
async def test_existing_access_does_not_attempt_password(version):
    paths=[]
    def respond(request):
        paths.append(request.url.path)
        assert request.method=='GET'
        if request.url.path=='/api/v2/app/version':
            return httpx.Response(200,text=version)
        return httpx.Response(200,json=[])
    c=QBittorrentClient(password='deliberately-wrong')
    c._client=httpx.AsyncClient(base_url='http://test',transport=httpx.MockTransport(respond))
    assert await c.login()
    assert await c.get_torrents()==[]
    assert paths==['/api/v2/app/version','/api/v2/torrents/info']
    await c.close()

@pytest.mark.asyncio
@pytest.mark.parametrize('probe_status,probe_body,login_body,expected',[
    (403,'Forbidden','Ok.',True),
    (403,'Forbidden','Fails.',False),
    (200,'<html>login</html>','Fails.',False),
    (200,'','Fails.',False),
])
async def test_password_fallback_and_invalid_probe(probe_status,probe_body,login_body,expected):
    paths=[]
    def respond(request):
        paths.append(request.url.path)
        if request.method=='GET':return httpx.Response(probe_status,text=probe_body)
        assert request.url.path=='/api/v2/auth/login'
        return httpx.Response(200,text=login_body)
    c=QBittorrentClient()
    c._client=httpx.AsyncClient(base_url='http://test',transport=httpx.MockTransport(respond))
    assert await c.login() is expected
    assert c._authenticated is expected
    assert paths==['/api/v2/app/version','/api/v2/auth/login']
    await c.close()
