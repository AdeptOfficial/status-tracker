"""Audit-event labels must not imply a new availability transition."""
import re
import pytest
from fastapi import FastAPI
from httpx import AsyncClient, ASGITransport
from app.database import get_db
from app.models import MediaRequest, MediaType, RequestState, TimelineEvent
from app.routers.pages import router
from app.services.auth import get_current_user

@pytest.mark.asyncio
@pytest.mark.parametrize('state,label', [(RequestState.AVAILABLE, 'Ready to Watch'),
                                         (RequestState.DOWNLOADING, 'Downloading'),
                                         (RequestState.ANIME_MATCHING, 'Matching')])
async def test_repair_label_is_distinct_from_lifecycle_state(db_session, state, label):
    row = MediaRequest(title='Synthetic movie', media_type=MediaType.MOVIE, state=state)
    db_session.add(row)
    await db_session.flush()
    for service, kind in [('library_sync', 'Import'), ('library_sync', 'Metadata repair'),
                          ('jellyfin', 'Metadata repair'), ('radarr', 'Import'), ('sonarr', 'Import')]:
        db_session.add(TimelineEvent(request_id=row.id, service=service, event_type=kind, state=state))
    await db_session.commit()
    app = FastAPI()
    app.include_router(router)
    async def db():
        yield db_session
    app.dependency_overrides[get_db] = db
    app.dependency_overrides[get_current_user] = lambda: None
    async with AsyncClient(transport=ASGITransport(app=app), base_url='http://test') as client:
        response = await client.get(f'/request/{row.id}')
    assert response.status_code == 200
    headings = re.findall(r'class="tl-head">\s*<b>(.*?)</b>', response.text)
    assert headings == [label, 'Metadata repaired', label, 'Imported', 'Imported']
    assert row.state == state
