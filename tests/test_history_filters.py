"""History filtering uses real routes/templates against isolated records."""
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from app.database import get_db
from app.models import MediaRequest, MediaType, RequestState
from app.routers.pages import router
from app.services.auth import get_current_user

@pytest.mark.asyncio
async def test_history_sources_counts_and_preserved_links(db_session):
    for name, user, state in [('Imported', 'Library Sync', RequestState.AVAILABLE),
                              ('Requested', 'alice & bob', RequestState.AVAILABLE),
                              ('Failed', 'alice & bob', RequestState.FAILED)]:
        db_session.add(MediaRequest(title=name, requested_by=user, state=state, media_type=MediaType.MOVIE))
    await db_session.commit()
    app = FastAPI()
    app.include_router(router)
    async def db(): yield db_session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_user] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        page = (await client.get('/history?source=library')).text
        assert '1 history item' in page and 'Ready (1)' in page and 'Failed (0)' in page
        assert 'value="Library Sync"' not in page
        assert 'source=library&amp;state=failed' in page
        assert 'id="user-filter" onchange="applyFilters()" disabled' in page
        page = (await client.get('/history', params={'user':'alice & bob','state':'failed','source':'requests'})).text
        assert '1 history item' in page and 'Ready (1)' in page and 'Failed (1)' in page
        assert 'user=alice+%26+bob&amp;source=requests&amp;state=available' in page
        assert 'No matching history' in (await client.get('/history?source=library&state=failed')).text
        assert '1 history item' in (await client.get('/history?user=Library%20Sync')).text

@pytest.mark.asyncio
async def test_history_total_is_not_limited_to_visible_cards(db_session):
    db_session.add_all([MediaRequest(title=f'Item {i}', state=RequestState.AVAILABLE, media_type=MediaType.MOVIE) for i in range(101)])
    await db_session.commit()
    app = FastAPI(); app.include_router(router)
    async def db(): yield db_session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_user] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        page = (await client.get('/history')).text
        assert '101 history items · showing latest 100' in page
        assert 'Ready (101)' in page
