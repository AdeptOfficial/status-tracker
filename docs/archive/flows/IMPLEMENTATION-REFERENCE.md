# Implementation Plan: Media Workflow Redesign (Merged)

**Goal:** Fix stuck requests and implement 4 media flows with proper testing.

**Design Principle:** Code should be easily extendable. Adding a new ID or field should be a simple change - not a refactor.

**Current Problems (from screenshot):**
- Lycoris Recoil: Stuck at "Importing", shows only "S01E01" (missing 12 episodes)
- Violet Evergarden: Stuck at "Matching" (ANIME_MATCHING never completes)

---

## Implementation Order

Test one flow at a time, building incrementally:

| Phase | Flow | Adds |
|-------|------|------|
| 0 | Test Infrastructure | pytest, fixtures, mocks |
| 1 | Database Updates | Episode table, state renames, new fields |
| 2 | Regular Movie | Core flow without episodes or Shoko |
| 3 | Regular TV | Episode table, per-episode tracking |
| 4 | Anime Movie | Shoko verification, multi-type fallback |
| 5 | Anime TV | Episode + Shoko combined |

---

## Phase 0: Test Infrastructure

### Create Test Structure

```
tests/
├── conftest.py              # DB fixtures, webhook loaders
├── fixtures/
│   └── webhooks/            # Symlink to docs/flows/captured-webhooks/
└── mocks/
    ├── qbittorrent.py       # Mock download progress
    ├── jellyfin.py          # Mock verification responses
    └── shoko.py             # Mock SignalR events
```

### conftest.py Essentials

```python
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
import json
from pathlib import Path

@pytest_asyncio.fixture
async def db_session():
    """In-memory SQLite async database."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session

@pytest.fixture
def load_webhook():
    """Load captured webhook JSON."""
    def _load(name: str) -> dict:
        path = Path(__file__).parent / "fixtures/webhooks" / f"{name}.json"
        return json.loads(path.read_text())
    return _load
```

### Requirements

Add to `requirements.txt`:
```
pytest
pytest-asyncio
aiosqlite
```

**Acceptance:** `pytest tests/` runs without errors

---

## Phase 1: Database Schema Updates

### 1.1 State Renames

**File:** `app/models.py`

```python
class RequestState(str, enum.Enum):
    REQUESTED = "requested"
    APPROVED = "approved"
    GRABBING = "grabbing"          # was INDEXED
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"      # was DOWNLOAD_DONE
    IMPORTING = "importing"
    ANIME_MATCHING = "anime_matching"
    AVAILABLE = "available"
    FAILED = "failed"

class EpisodeState(str, enum.Enum):
    GRABBING = "grabbing"
    DOWNLOADING = "downloading"
    DOWNLOADED = "downloaded"
    IMPORTING = "importing"
    ANIME_MATCHING = "anime_matching"
    AVAILABLE = "available"
    FAILED = "failed"
```

### 1.2 MediaRequest New Fields

```python
# Detection flag
is_anime: Mapped[Optional[bool]] = mapped_column(default=None)

# IDs from Radarr/Sonarr Grab
imdb_id: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)

# Content info
overview: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
original_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)  # Post-MVP

# Release info from Grab
file_size: Mapped[Optional[int]] = mapped_column(nullable=True)  # bytes
release_group: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

# TV-specific
requested_seasons: Mapped[Optional[str]] = mapped_column(String(50), default=None)  # "1" or "1,2,3"
total_episodes: Mapped[Optional[int]] = mapped_column(default=None)

# Completion timestamp
available_at: Mapped[Optional[datetime]] = mapped_column(default=None)

# Relationship to episodes
episodes: Mapped[list["Episode"]] = relationship(back_populates="request", cascade="all, delete-orphan")
```

### 1.3 Episode Model (NEW)

```python
class Episode(Base):
    __tablename__ = "episodes"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("requests.id"), index=True)

    # Episode identification
    season_number: Mapped[int]
    episode_number: Mapped[int]
    episode_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Service IDs (from Sonarr Grab webhook)
    sonarr_episode_id: Mapped[Optional[int]] = mapped_column(nullable=True)
    episode_tvdb_id: Mapped[Optional[int]] = mapped_column(nullable=True)

    # State tracking
    state: Mapped[EpisodeState] = mapped_column(default=EpisodeState.GRABBING)

    # Download tracking (shared for season packs)
    qbit_hash: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, index=True)

    # File path (from Sonarr Import)
    final_path: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)

    # Anime matching (from Shoko)
    shoko_file_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Jellyfin (from verification)
    jellyfin_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationship
    request: Mapped["MediaRequest"] = relationship(back_populates="episodes")
```

### 1.4 Field Population Map

**Request Fields:**

| Field | Populated By | Webhook Field |
|-------|--------------|---------------|
| `jellyseerr_id` | Jellyseerr | `request.request_id` |
| `tmdb_id` | Jellyseerr | `media.tmdbId` |
| `tvdb_id` | Jellyseerr (TV) | `media.tvdbId` |
| `requested_seasons` | Jellyseerr (TV) | `extra[0].value` |
| `overview` | Jellyseerr | `message` |
| `radarr_id` | Radarr Grab | `movie.id` |
| `sonarr_id` | Sonarr Grab | `series.id` |
| `imdb_id` | Radarr/Sonarr Grab | `movie.imdbId` / `series.imdbId` |
| `qbit_hash` | Radarr/Sonarr Grab | `downloadId` |
| `is_anime` | Radarr/Sonarr Grab | `movie.tags` / `series.type` |
| `file_size` | Radarr/Sonarr Grab | `release.size` |
| `release_group` | Radarr/Sonarr Grab | `release.releaseGroup` |
| `final_path` | Radarr/Sonarr Import | `movieFile.path` |
| `jellyfin_id` | Jellyfin Verify | `Items[0].Id` |
| `shoko_series_id` | Shoko FileMatched | (from cross-refs) |
| `original_title` | Post-MVP (TMDB API) | - |

**Episode Fields:**

| Field | Populated By | Webhook Field |
|-------|--------------|---------------|
| `sonarr_episode_id` | Sonarr Grab | `episodes[].id` |
| `episode_tvdb_id` | Sonarr Grab | `episodes[].tvdbId` |
| `episode_title` | Sonarr Grab | `episodes[].title` |
| `qbit_hash` | Sonarr Grab | `downloadId` (same for all in pack) |
| `final_path` | Sonarr Import | `episodeFiles[].path` |
| `shoko_file_id` | Shoko FileMatched | `FileInfo.FileID` |
| `jellyfin_id` | Jellyfin Verify | episode item ID |

### 1.5 State Machine Updates

**File:** `app/core/state_machine.py`

Update `VALID_TRANSITIONS` with new state names:

```python
VALID_TRANSITIONS = {
    RequestState.REQUESTED: [RequestState.APPROVED, RequestState.FAILED],
    RequestState.APPROVED: [RequestState.GRABBING, RequestState.FAILED],
    RequestState.GRABBING: [RequestState.DOWNLOADING, RequestState.FAILED],
    RequestState.DOWNLOADING: [RequestState.DOWNLOADED, RequestState.FAILED],
    RequestState.DOWNLOADED: [RequestState.IMPORTING, RequestState.ANIME_MATCHING, RequestState.FAILED],
    RequestState.IMPORTING: [RequestState.AVAILABLE, RequestState.FAILED],
    RequestState.ANIME_MATCHING: [RequestState.AVAILABLE, RequestState.FAILED],
    RequestState.AVAILABLE: [RequestState.FAILED],  # For manual override
    RequestState.FAILED: [RequestState.APPROVED],   # For retry
}
```

**Acceptance:** App starts, Episode table created, all ID fields present

---

## Phase 2: Flow 1 - Regular Movie

**Flow:** `APPROVED → GRABBING → DOWNLOADING → DOWNLOADED → IMPORTING → AVAILABLE`

### 2.1 Bug Fixes Required

**File:** `app/core/correlator.py` (Line ~15)

```python
# BUG: AVAILABLE in active states causes matching old requests
# BEFORE (broken):
ACTIVE_STATES = [REQUESTED, APPROVED, GRABBING, DOWNLOADING, DOWNLOADED, IMPORTING, ANIME_MATCHING, AVAILABLE]

# AFTER (fixed):
ACTIVE_STATES = [REQUESTED, APPROVED, GRABBING, DOWNLOADING, DOWNLOADED, IMPORTING, ANIME_MATCHING]
# Remove AVAILABLE, FAILED, TIMEOUT from this list
```

**File:** `app/plugins/jellyseerr.py`

```python
# Fix poster URL extraction
# BEFORE (broken):
poster_url = extra.get("Poster")

# AFTER (fixed):
poster_url = payload.get("image")

# Parse year from subject
import re
subject = payload.get("subject", "")
year_match = re.search(r"\((\d{4})\)", subject)
year = int(year_match.group(1)) if year_match else None
```

### 2.2 Radarr Grab Handler

**File:** `app/plugins/radarr.py`

```python
async def _handle_grab(self, request: MediaRequest, payload: dict, db: AsyncSession):
    """Handle Radarr Grab webhook."""
    movie = payload.get("movie", {})
    release = payload.get("release", {})

    # Store correlation data
    request.qbit_hash = payload.get("downloadId")
    request.radarr_id = movie.get("id")
    request.imdb_id = movie.get("imdbId")

    # Detect is_anime from tags
    tags = movie.get("tags", [])
    request.is_anime = "anime" in [t.lower() for t in tags]

    # Release info
    request.quality = release.get("quality")
    request.indexer = release.get("indexer")
    request.file_size = release.get("size")
    request.release_group = release.get("releaseGroup")

    # Transition state: APPROVED → GRABBING
    request.state = RequestState.GRABBING
```

### 2.3 Radarr Import Handler

**File:** `app/plugins/radarr.py`

```python
async def _handle_import(self, request: MediaRequest, payload: dict, db: AsyncSession):
    """Handle Radarr Import (Download) webhook."""
    movie_file = payload.get("movieFile", {})

    # Store final path - CRITICAL for Shoko correlation
    request.final_path = movie_file.get("path")

    # Verify/update is_anime from path if not already set
    if request.is_anime is None:
        request.is_anime = "/anime/" in request.final_path.lower()

    # Transition based on anime flag
    if request.is_anime:
        request.state = RequestState.ANIME_MATCHING
    else:
        request.state = RequestState.IMPORTING
```

### 2.4 Regular Movie Verification

**File:** `app/services/jellyfin_verifier.py`

```python
async def verify_regular_movie(request: MediaRequest, db: AsyncSession) -> bool:
    """Verify non-anime movie in Jellyfin by TMDB ID."""
    if not request.tmdb_id:
        return False

    item = await jellyfin.find_item_by_provider_id("Tmdb", request.tmdb_id, "Movie")

    if item and is_playable(item):
        request.jellyfin_id = item["Id"]
        request.state = RequestState.AVAILABLE
        request.available_at = datetime.utcnow()
        return True

    return False

def is_playable(item: dict) -> bool:
    """Check if Jellyfin item is actually playable (not metadata-only)."""
    return bool(item.get("MediaSources") or item.get("Path"))
```

### 2.5 Tests

**File:** `tests/test_flow_1_regular_movie.py`

```python
import pytest
from app.models import MediaRequest, RequestState

@pytest.mark.asyncio
async def test_regular_movie_full_flow(db_session, load_webhook):
    """Test complete flow: APPROVED → AVAILABLE."""
    # 1. Jellyseerr auto-approve webhook → creates request (APPROVED)
    jellyseerr_payload = load_webhook("jellyseerr-movie")
    request = await handle_jellyseerr_webhook(jellyseerr_payload, db_session)
    assert request.state == RequestState.APPROVED
    assert request.tmdb_id == 533514

    # 2. Radarr grab webhook → GRABBING, qbit_hash set, is_anime=False
    radarr_grab = load_webhook("radarr-grab")
    await handle_radarr_webhook(radarr_grab, db_session)
    assert request.state == RequestState.GRABBING
    assert request.qbit_hash == "C2C60F66C126652A86F7F2EE73DC83D4E255929E"
    assert request.is_anime == True  # Has anime tag

    # 3. Mock qBit progress → DOWNLOADING → DOWNLOADED
    await update_download_progress(request, 0.5, db_session)
    assert request.state == RequestState.DOWNLOADING

    await update_download_progress(request, 1.0, db_session)
    assert request.state == RequestState.DOWNLOADED

    # 4. Radarr import webhook → IMPORTING (or ANIME_MATCHING if anime)
    radarr_import = load_webhook("radarr-import")
    await handle_radarr_webhook(radarr_import, db_session)
    # Since is_anime=True, goes to ANIME_MATCHING
    assert request.state == RequestState.ANIME_MATCHING

    # 5. Mock Jellyfin finds by TMDB → AVAILABLE
    await verify_request(request, db_session)
    assert request.state == RequestState.AVAILABLE

@pytest.mark.asyncio
async def test_correlation_excludes_available(db_session, load_webhook):
    """Verify old AVAILABLE requests don't match new webhooks."""
    # Create old AVAILABLE request for same TMDB
    old_request = MediaRequest(
        tmdb_id=533514,
        state=RequestState.AVAILABLE,
        title="Old Request"
    )
    db_session.add(old_request)
    await db_session.commit()

    # New webhook should create NEW request, not match old one
    jellyseerr_payload = load_webhook("jellyseerr-movie")
    new_request = await handle_jellyseerr_webhook(jellyseerr_payload, db_session)

    assert new_request.id != old_request.id
    assert new_request.state == RequestState.APPROVED
```

**Acceptance:** Regular movie reaches AVAILABLE, correlation bug fixed

---

## Phase 3: Flow 2 - Regular TV

**Flow:** Same states, but with Episode table

### 3.1 Sonarr Grab Handler (Episode Creation)

**File:** `app/plugins/sonarr.py`

```python
async def _handle_grab(self, request: MediaRequest, payload: dict, db: AsyncSession):
    """Handle Sonarr Grab webhook - creates Episode rows."""
    series = payload.get("series", {})
    release = payload.get("release", {})
    download_id = payload.get("downloadId")
    episodes_data = payload.get("episodes", [])

    # Store correlation data
    request.qbit_hash = download_id
    request.sonarr_id = series.get("id")
    request.imdb_id = series.get("imdbId")

    # Detect is_anime from series type
    request.is_anime = series.get("type") == "anime"

    # Release info
    request.quality = release.get("quality")
    request.indexer = release.get("indexer")
    request.file_size = release.get("size")
    request.release_group = release.get("releaseGroup")

    # CREATE EPISODE ROWS from webhook data (no API call needed!)
    for ep in episodes_data:
        episode = Episode(
            request_id=request.id,
            season_number=ep["seasonNumber"],
            episode_number=ep["episodeNumber"],
            episode_title=ep.get("title"),
            sonarr_episode_id=ep.get("id"),
            episode_tvdb_id=ep.get("tvdbId"),
            qbit_hash=download_id,  # All share same hash for season pack
            state=EpisodeState.GRABBING
        )
        db.add(episode)

    request.total_episodes = len(episodes_data)
    request.state = RequestState.GRABBING
```

### 3.2 Sonarr Import Handler (Season Pack Support)

**File:** `app/plugins/sonarr.py`

```python
async def _handle_import(self, request: MediaRequest, payload: dict, db: AsyncSession):
    """Handle Sonarr Import (Download) webhook."""
    # Season pack: episodeFiles[] (plural) - ONE webhook for all
    # Single episode: episodeFile (singular) - one webhook per episode
    episode_files = payload.get("episodeFiles", [])
    if not episode_files:
        single = payload.get("episodeFile")
        if single:
            episode_files = [single]

    episodes_data = payload.get("episodes", [])

    # Match episodes to files by index (they're in the same order)
    for i, ep_data in enumerate(episodes_data):
        episode = await db.execute(
            select(Episode).where(
                Episode.request_id == request.id,
                Episode.season_number == ep_data["seasonNumber"],
                Episode.episode_number == ep_data["episodeNumber"]
            )
        )
        episode = episode.scalar_one_or_none()

        if episode and i < len(episode_files):
            episode.final_path = episode_files[i].get("path")

            if request.is_anime:
                episode.state = EpisodeState.ANIME_MATCHING
            else:
                episode.state = EpisodeState.IMPORTING

    # Update request final_path to series folder
    request.final_path = payload.get("destinationPath") or payload.get("series", {}).get("path")

    # Recalculate aggregate state
    request.state = calculate_aggregate_state(request)
```

### 3.3 State Aggregation

**File:** `app/services/state_calculator.py` (NEW)

```python
def calculate_aggregate_state(request: MediaRequest) -> RequestState:
    """Derive request state from episode states."""
    if request.media_type == "movie":
        return request.state  # No aggregation needed

    episodes = request.episodes
    if not episodes:
        return request.state

    states = [ep.state for ep in episodes]

    # All available → available
    if all(s == EpisodeState.AVAILABLE for s in states):
        return RequestState.AVAILABLE

    # Any failed → failed
    if any(s == EpisodeState.FAILED for s in states):
        return RequestState.FAILED

    # Priority order for in-progress states (highest priority first)
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

    return request.state
```

### 3.4 qBit Poller Updates

**File:** `app/plugins/qbittorrent.py`

**Adaptive polling (from MVP Q10):**
```python
POLL_FAST = 5   # seconds when downloads active
POLL_SLOW = 30  # seconds when idle

async def get_poll_interval(db: AsyncSession) -> int:
    """Return polling interval based on active downloads."""
    active = await db.scalar(
        select(func.count()).where(
            MediaRequest.state.in_([RequestState.GRABBING, RequestState.DOWNLOADING])
        )
    )
    return POLL_FAST if active > 0 else POLL_SLOW

async def polling_loop(db: AsyncSession):
    """Main polling loop with adaptive interval."""
    while True:
        await update_download_progress(db)
        interval = await get_poll_interval(db)
        await asyncio.sleep(interval)
```

**Progress updates:**
```python
async def update_download_progress(db: AsyncSession):
    """Poll qBit and update request/episode states."""
    torrents = await qbit_client.get_torrents()

    for torrent in torrents:
        hash_upper = torrent["hash"].upper()
        progress = torrent["progress"]  # 0.0 to 1.0

        # Find all episodes with this hash (for season packs)
        episodes = await db.execute(
            select(Episode).where(Episode.qbit_hash == hash_upper)
        )
        episodes = episodes.scalars().all()

        for episode in episodes:
            if progress < 1.0:
                episode.state = EpisodeState.DOWNLOADING
            else:
                episode.state = EpisodeState.DOWNLOADED

        # Find requests with this hash (for movies)
        requests = await db.execute(
            select(MediaRequest).where(MediaRequest.qbit_hash == hash_upper)
        )
        for request in requests.scalars():
            request.download_progress = int(progress * 100)

            if request.media_type == "movie":
                if progress < 1.0:
                    request.state = RequestState.DOWNLOADING
                else:
                    request.state = RequestState.DOWNLOADED
            else:
                # TV: recalculate from episodes
                request.state = calculate_aggregate_state(request)
```

### 3.5 Jellyfin Client - TVDB Lookup

**File:** `app/clients/jellyfin.py`

```python
async def find_item_by_provider_id(
    self,
    provider: str,  # "Tmdb" or "Tvdb"
    provider_id: int,
    item_type: str = None  # "Movie", "Series", or None for any
) -> Optional[dict]:
    """Generic provider ID lookup."""
    params = {
        "AnyProviderIdEquals": f"{provider}.{provider_id}",
        "Recursive": "true",
    }
    if item_type:
        params["IncludeItemTypes"] = item_type

    response = await self.get("/Items", params=params)
    items = response.get("Items", [])

    # Return first playable match with exact provider ID
    for item in items:
        provider_ids = item.get("ProviderIds", {})
        if str(provider_ids.get(provider)) == str(provider_id):
            if is_playable(item):
                return item

    return None
```

### 3.6 Regular TV Verification

**File:** `app/services/jellyfin_verifier.py`

```python
async def verify_regular_tv(request: MediaRequest, db: AsyncSession) -> bool:
    """Verify non-anime TV series in Jellyfin."""
    # Try TVDB first (preferred for TV)
    if request.tvdb_id:
        item = await jellyfin.find_item_by_provider_id("Tvdb", request.tvdb_id, "Series")
        if item and is_playable(item):
            return await mark_tv_available(request, item, db)

    # Fallback to TMDB
    if request.tmdb_id:
        item = await jellyfin.find_item_by_provider_id("Tmdb", request.tmdb_id, "Series")
        if item and is_playable(item):
            return await mark_tv_available(request, item, db)

    return False

async def mark_tv_available(request: MediaRequest, item: dict, db: AsyncSession) -> bool:
    """Mark TV request and all episodes as available."""
    request.jellyfin_id = item["Id"]
    request.state = RequestState.AVAILABLE
    request.available_at = datetime.utcnow()

    # Mark all episodes available (series-level verification for MVP)
    for episode in request.episodes:
        episode.state = EpisodeState.AVAILABLE

    return True
```

### 3.7 Fix Fallback Checker (Bug #2)

**File:** `app/services/jellyfin_verifier.py`

```python
async def run_fallback_verification(db: AsyncSession):
    """Check all stuck requests - FIX: include TV!"""
    stmt = select(MediaRequest).where(
        MediaRequest.state.in_([
            RequestState.IMPORTING,
            RequestState.ANIME_MATCHING,
        ]),
        MediaRequest.updated_at < datetime.utcnow() - timedelta(minutes=5),
        # NO media_type filter - check both movies AND TV
    )

    result = await db.execute(stmt)
    requests = result.scalars().all()

    for request in requests:
        await verify_request(request, db)
```

### 3.8 Tests

**File:** `tests/test_flow_2_regular_tv.py`

```python
@pytest.mark.asyncio
async def test_regular_tv_episode_creation(db_session, load_webhook):
    """Verify Episode rows created from Grab webhook."""
    # Setup: Create request from Jellyseerr
    request = MediaRequest(tvdb_id=414057, state=RequestState.APPROVED, media_type="tv")
    db_session.add(request)
    await db_session.commit()

    # Sonarr Grab webhook
    grab_payload = load_webhook("sonarr-grab")
    await handle_sonarr_webhook(grab_payload, db_session)

    # Verify 13 episodes created
    assert len(request.episodes) == 13
    assert all(ep.qbit_hash == grab_payload["downloadId"] for ep in request.episodes)
    assert request.episodes[0].episode_title == "Easy does it"

@pytest.mark.asyncio
async def test_season_pack_import(db_session, load_webhook):
    """Season pack Import = ONE webhook updates all episodes."""
    # Setup request with episodes
    # ... (setup code)

    # Sonarr Import webhook (season pack)
    import_payload = load_webhook("sonarr-import")
    await handle_sonarr_webhook(import_payload, db_session)

    # All 13 episodes should have final_path
    for episode in request.episodes:
        assert episode.final_path is not None
        assert episode.state == EpisodeState.IMPORTING

@pytest.mark.asyncio
async def test_episode_state_aggregation(db_session):
    """Request.state derived from Episode states."""
    request = MediaRequest(media_type="tv", state=RequestState.GRABBING)
    db_session.add(request)

    # Add episodes with mixed states
    for i in range(5):
        ep = Episode(request=request, season_number=1, episode_number=i+1)
        ep.state = EpisodeState.AVAILABLE if i < 3 else EpisodeState.IMPORTING
        db_session.add(ep)

    await db_session.commit()

    # Aggregate should be IMPORTING (not all available yet)
    assert calculate_aggregate_state(request) == RequestState.IMPORTING
```

**Acceptance:** 13 episodes created, all reach AVAILABLE

---

## Phase 4: Flow 3 - Anime Movie

**Flow:** `... → IMPORTING → ANIME_MATCHING → AVAILABLE`

### 4.1 Anime Detection Already Done

Anime detection happens at Grab (Phase 2) from `movie.tags`. The Import handler (Phase 2.3) already routes to `ANIME_MATCHING` state.

### 4.2 Multi-Type Fallback Verification

**File:** `app/services/jellyfin_verifier.py`

```python
async def verify_anime_movie(request: MediaRequest, db: AsyncSession) -> bool:
    """
    Verify anime movie - may be recategorized by Shoko.

    Problem: Jellyseerr requests as Movie (TMDB), but Shoko/AniDB may
    categorize as TV Special. Shokofin then presents as TV episode.

    Solution: Try multiple item types.
    """
    # Try 1: Movie by TMDB (expected type)
    if request.tmdb_id:
        item = await jellyfin.find_item_by_provider_id("Tmdb", request.tmdb_id, "Movie")
        if item and is_playable(item):
            return await mark_available(request, item, db)

    # Try 2: Series by TMDB (Shoko may categorize as TV)
    if request.tmdb_id:
        item = await jellyfin.find_item_by_provider_id("Tmdb", request.tmdb_id, "Series")
        if item and is_playable(item):
            return await mark_available(request, item, db)

    # Try 3: Any type by TMDB (no type filter)
    if request.tmdb_id:
        item = await jellyfin.find_item_by_provider_id("Tmdb", request.tmdb_id)
        if item and is_playable(item):
            return await mark_available(request, item, db)

    # Try 4: Title search (last resort)
    item = await jellyfin.search_by_title(request.title, request.year)
    if item and is_playable(item):
        return await mark_available(request, item, db)

    return False

async def mark_available(request: MediaRequest, item: dict, db: AsyncSession) -> bool:
    """Mark request as available."""
    request.jellyfin_id = item["Id"]
    request.state = RequestState.AVAILABLE
    request.available_at = datetime.utcnow()
    return True
```

### 4.3 Shoko FileMatched Handler

**File:** `app/plugins/shoko.py`

```python
async def handle_file_matched(event: dict, db: AsyncSession):
    """Handle Shoko FileMatched SignalR event for movies."""
    file_info = event.get("FileInfo", {})
    relative_path = file_info.get("RelativePath", "")
    has_cross_refs = bool(file_info.get("CrossReferences"))

    # Find matching request by path
    request = await find_request_by_path(relative_path, db)
    if not request:
        logger.warning(f"No request found for Shoko file: {relative_path}")
        return

    if request.media_type != "movie":
        return  # TV handled separately

    if has_cross_refs:
        # Fully matched to AniDB - trigger verification
        request.shoko_series_id = extract_series_id(file_info)
        await verify_anime_movie(request, db)
    else:
        # File detected but not yet matched - stay in ANIME_MATCHING
        request.state = RequestState.ANIME_MATCHING

def find_request_by_path(relative_path: str, db: AsyncSession) -> MediaRequest | None:
    """Match Shoko's RelativePath to request's final_path."""
    # Shoko sends: "anime/movies/Title/file.mkv"
    # Our final_path: "/data/anime/movies/Title/file.mkv"

    requests = await db.execute(
        select(MediaRequest).where(
            MediaRequest.state.in_([RequestState.IMPORTING, RequestState.ANIME_MATCHING]),
            MediaRequest.final_path.isnot(None)
        )
    )

    for request in requests.scalars():
        # Primary: Path ends with Shoko's relative path
        if request.final_path.endswith(relative_path):
            return request

        # Fallback: Filename match
        if os.path.basename(request.final_path) == os.path.basename(relative_path):
            return request

    return None
```

### 4.4 Tests

**File:** `tests/test_flow_3_anime_movie.py`

```python
@pytest.mark.asyncio
async def test_anime_movie_detection(db_session, load_webhook):
    """is_anime=True detected from movie.tags."""
    request = MediaRequest(tmdb_id=533514, state=RequestState.APPROVED, media_type="movie")
    db_session.add(request)

    grab_payload = load_webhook("radarr-grab")
    await handle_radarr_webhook(grab_payload, db_session)

    assert request.is_anime == True  # "anime" in movie.tags

@pytest.mark.asyncio
async def test_anime_movie_goes_through_matching(db_session, load_webhook):
    """Anime movie goes through ANIME_MATCHING state."""
    # Setup with is_anime=True
    request = MediaRequest(tmdb_id=533514, state=RequestState.DOWNLOADED, is_anime=True, media_type="movie")
    db_session.add(request)

    import_payload = load_webhook("radarr-import")
    await handle_radarr_webhook(import_payload, db_session)

    assert request.state == RequestState.ANIME_MATCHING

@pytest.mark.asyncio
async def test_anime_movie_recategorization_fallback(db_session, mock_jellyfin):
    """If Shoko categorizes as TV, fallback finds it."""
    request = MediaRequest(
        tmdb_id=1052946,  # Violet Evergarden: Recollections
        state=RequestState.ANIME_MATCHING,
        is_anime=True,
        media_type="movie"
    )
    db_session.add(request)

    # Mock: Movie search returns nothing
    mock_jellyfin.find_item_by_provider_id.side_effect = [
        None,  # Try 1: Movie by TMDB - not found
        {"Id": "abc123", "Type": "Series", "MediaSources": [{}]},  # Try 2: Series - FOUND!
    ]

    result = await verify_anime_movie(request, db_session)

    assert result == True
    assert request.state == RequestState.AVAILABLE
    assert request.jellyfin_id == "abc123"
```

**Acceptance:** Anime movie reaches AVAILABLE via Shoko or fallback

---

## Phase 5: Flow 4 - Anime TV

**Flow:** Episodes go through `ANIME_MATCHING` individually

### 5.1 Sonarr Import for Anime TV

Already handled in Phase 3.2 - sets `episode.state = EpisodeState.ANIME_MATCHING` when `request.is_anime=True`.

### 5.2 Shoko FileMatched for TV Episodes

**File:** `app/plugins/shoko.py`

```python
async def handle_file_matched_tv(event: dict, db: AsyncSession):
    """Handle Shoko FileMatched for TV episodes."""
    file_info = event.get("FileInfo", {})
    relative_path = file_info.get("RelativePath", "")
    has_cross_refs = bool(file_info.get("CrossReferences"))

    # Find matching episode by path
    episode = await find_episode_by_path(relative_path, db)
    if not episode:
        logger.warning(f"No episode found for Shoko file: {relative_path}")
        return

    if has_cross_refs:
        # Matched to AniDB
        episode.shoko_file_id = str(file_info.get("FileID"))
        episode.state = EpisodeState.AVAILABLE
    else:
        episode.state = EpisodeState.ANIME_MATCHING

    # Recalculate parent request state
    request = episode.request
    request.state = calculate_aggregate_state(request)

    # If all episodes available, verify in Jellyfin
    if request.state == RequestState.AVAILABLE:
        await verify_anime_tv(request, db)

async def find_episode_by_path(relative_path: str, db: AsyncSession) -> Episode | None:
    """Match Shoko's RelativePath to episode's final_path."""
    episodes = await db.execute(
        select(Episode).where(
            Episode.state.in_([EpisodeState.IMPORTING, EpisodeState.ANIME_MATCHING]),
            Episode.final_path.isnot(None)
        )
    )

    for episode in episodes.scalars():
        if episode.final_path.endswith(relative_path):
            return episode
        if os.path.basename(episode.final_path) == os.path.basename(relative_path):
            return episode

    return None
```

### 5.3 Anime TV Verification

**File:** `app/services/jellyfin_verifier.py`

```python
async def verify_anime_tv(request: MediaRequest, db: AsyncSession) -> bool:
    """Verify anime TV series - may be recategorized."""
    # Try 1: Series by TVDB
    if request.tvdb_id:
        item = await jellyfin.find_item_by_provider_id("Tvdb", request.tvdb_id, "Series")
        if item and is_playable(item):
            return await mark_tv_available(request, item, db)

    # Try 2: Series by TMDB
    if request.tmdb_id:
        item = await jellyfin.find_item_by_provider_id("Tmdb", request.tmdb_id, "Series")
        if item and is_playable(item):
            return await mark_tv_available(request, item, db)

    # Try 3: Any type by TMDB
    if request.tmdb_id:
        item = await jellyfin.find_item_by_provider_id("Tmdb", request.tmdb_id)
        if item and is_playable(item):
            return await mark_tv_available(request, item, db)

    # Try 4: Title search
    item = await jellyfin.search_by_title(request.title)
    if item and is_playable(item):
        return await mark_tv_available(request, item, db)

    return False
```

### 5.4 Unified Verification Router

**File:** `app/services/jellyfin_verifier.py`

```python
async def verify_request(request: MediaRequest, db: AsyncSession) -> bool:
    """Route to appropriate verification path based on is_anime and media_type."""
    if request.is_anime:
        if request.media_type == "movie":
            return await verify_anime_movie(request, db)    # Path 5c
        else:
            return await verify_anime_tv(request, db)       # Path 5d
    else:
        if request.media_type == "movie":
            return await verify_regular_movie(request, db)  # Path 5a
        else:
            return await verify_regular_tv(request, db)     # Path 5b
```

### 5.5 Tests

**File:** `tests/test_flow_4_anime_tv.py`

```python
@pytest.mark.asyncio
async def test_anime_tv_detection(db_session, load_webhook):
    """is_anime=True from series.type."""
    request = MediaRequest(tvdb_id=414057, state=RequestState.APPROVED, media_type="tv")
    db_session.add(request)

    grab_payload = load_webhook("sonarr-grab")
    await handle_sonarr_webhook(grab_payload, db_session)

    assert request.is_anime == True  # series.type == "anime"

@pytest.mark.asyncio
async def test_anime_tv_episodes_anime_matching(db_session, load_webhook):
    """13 episodes created at ANIME_MATCHING state."""
    # Setup with grab
    request = MediaRequest(tvdb_id=414057, state=RequestState.APPROVED, media_type="tv")
    db_session.add(request)
    grab_payload = load_webhook("sonarr-grab")
    await handle_sonarr_webhook(grab_payload, db_session)

    # Import
    import_payload = load_webhook("sonarr-import")
    await handle_sonarr_webhook(import_payload, db_session)

    # All episodes should be ANIME_MATCHING
    assert all(ep.state == EpisodeState.ANIME_MATCHING for ep in request.episodes)
    assert request.state == RequestState.ANIME_MATCHING

@pytest.mark.asyncio
async def test_anime_tv_partial_progress(db_session):
    """If only 5/13 matched, request shows partial progress."""
    request = MediaRequest(media_type="tv", is_anime=True, state=RequestState.ANIME_MATCHING)
    db_session.add(request)

    for i in range(13):
        ep = Episode(request=request, season_number=1, episode_number=i+1)
        ep.state = EpisodeState.AVAILABLE if i < 5 else EpisodeState.ANIME_MATCHING
        db_session.add(ep)

    await db_session.commit()

    # Still ANIME_MATCHING until all episodes done
    assert calculate_aggregate_state(request) == RequestState.ANIME_MATCHING

@pytest.mark.asyncio
async def test_anime_tv_all_episodes_available(db_session, mock_jellyfin):
    """All 13 episodes matched → request AVAILABLE."""
    request = MediaRequest(media_type="tv", is_anime=True, tvdb_id=414057, state=RequestState.ANIME_MATCHING)
    db_session.add(request)

    for i in range(13):
        ep = Episode(request=request, season_number=1, episode_number=i+1, state=EpisodeState.AVAILABLE)
        db_session.add(ep)

    await db_session.commit()

    mock_jellyfin.find_item_by_provider_id.return_value = {"Id": "series123", "MediaSources": [{}]}

    await verify_request(request, db_session)

    assert request.state == RequestState.AVAILABLE
    assert request.jellyfin_id == "series123"
```

**Acceptance:** All 13 episodes reach AVAILABLE

---

## Files Summary

| Action | File | Phase |
|--------|------|-------|
| CREATE | `tests/conftest.py` | 0 |
| CREATE | `tests/mocks/` | 0 |
| CREATE | `app/models/episode.py` or update `app/models.py` | 1 |
| CREATE | `app/services/state_calculator.py` | 3 |
| CREATE | `tests/test_flow_1_regular_movie.py` | 2 |
| CREATE | `tests/test_flow_2_regular_tv.py` | 3 |
| CREATE | `tests/test_flow_3_anime_movie.py` | 4 |
| CREATE | `tests/test_flow_4_anime_tv.py` | 5 |
| MODIFY | `app/core/correlator.py` | 2 |
| MODIFY | `app/core/state_machine.py` | 1 |
| MODIFY | `app/plugins/jellyseerr.py` | 2 |
| MODIFY | `app/plugins/radarr.py` | 2 |
| MODIFY | `app/plugins/sonarr.py` | 3 |
| MODIFY | `app/plugins/qbittorrent.py` | 3 |
| MODIFY | `app/plugins/shoko.py` | 4, 5 |
| MODIFY | `app/clients/jellyfin.py` | 3 |
| MODIFY | `app/services/jellyfin_verifier.py` | 2, 3, 4, 5 |

---

## Extensibility Guidelines

The code should make it trivial to add new fields. Here's the pattern:

### Adding a New Field (Example: `release_title`)

**Step 1: Add to model** (`app/models.py`)
```python
release_title: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
```

**Step 2: Extract in webhook handler** (`app/plugins/radarr.py`)
```python
# In _handle_grab():
request.release_title = payload.get("release", {}).get("releaseTitle")
```

**Done.** No other changes needed.

### Why This Works

1. **Flat extraction** - Webhook handlers directly map fields, no abstraction layers
2. **Optional fields** - All new fields default to `nullable=True`
3. **No migrations for dev** - SQLite auto-creates columns in dev mode
4. **Field maps are documentation** - The tables in Phase 1 document where data comes from, but code isn't generated from them

### Anti-Patterns to Avoid

```python
# BAD: Over-abstracted field mapping
FIELD_MAP = {"release_title": "release.releaseTitle"}
for field, path in FIELD_MAP.items():
    setattr(request, field, get_nested(payload, path))

# GOOD: Direct and obvious
request.release_title = payload.get("release", {}).get("releaseTitle")
```

The direct approach is:
- Easier to debug (set breakpoint on exact line)
- Easier to extend (copy-paste one line)
- Easier to understand (no indirection)

---

## Verification Checklist

After each phase, run:
```bash
pytest tests/test_flow_N_*.py -v
```

After all phases:
```bash
# Full test suite
pytest tests/ -v

# Deploy to dev
./deploy.sh dev

# Test with real requests (new ones, not stuck ones)
# Verify stuck requests can be manually transitioned or deleted
```

---

## Definition of Done

- [ ] All 4 test files pass
- [ ] State names corrected (GRABBING, DOWNLOADED)
- [ ] Episode table works for TV
- [ ] Correlation bug fixed (AVAILABLE not in active states)
- [ ] TV fallback working (no media_type filter)
- [ ] Anime detection at Grab time
- [ ] Multi-type fallback for recategorized anime
- [ ] Lycoris Recoil reaches AVAILABLE with 13 episodes
- [ ] Violet Evergarden: Recollections reaches AVAILABLE
- [ ] No new requests stuck at IMPORTING or MATCHING after 10 minutes
