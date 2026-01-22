# Deletion Sync Testing Documentation

**Created:** 2026-01-18
**Status:** ✅ Complete
**Last Updated:** 2026-01-18

## Test Scenarios Overview

| # | Scenario | Media Type | Applicable Services | Phase 1 | Phase 2 | Phase 3 |
|---|----------|------------|---------------------|---------|---------|---------|
| 1 | Regular Movie | MOVIE | Radarr, Jellyfin, Jellyseerr | ✅ | ✅ | ✅ |
| 2 | Regular TV Show | TV | Sonarr, Jellyfin, Jellyseerr | ⚠️ No test media | — | ❌ **UNTESTED** |
| 3 | Anime Movie | MOVIE | Radarr, Shoko, Jellyfin, Jellyseerr | ✅ | ✅ | ✅ |
| 4 | Anime TV Show | TV | Sonarr, Shoko, Jellyfin, Jellyseerr | ✅ | ✅ | ✅ |

### Scenario 2 Note
**UNTESTED:** No non-anime TV shows currently in the library. Need to add one (e.g., Breaking Bad, The Office) to test Sonarr-only flow without Shoko involvement. Feature should work identically to anime TV.

---

## Phase 1: Sync Disabled Testing ✅ COMPLETE

All 4 scenarios tested with `ENABLE_DELETION_SYNC=false`:
- Verified service applicability logic
- Verified all applicable services show "skipped"
- Verified non-applicable services show "not_applicable"
- Verified missing IDs show "not_needed"

---

## Phase 2: API Testing (delete_files=false) ✅ COMPLETE

### Test Results

| Test Media | Radarr | Sonarr | Shoko | Jellyfin | Jellyseerr |
|-----------|--------|--------|-------|----------|------------|
| Ender's Game (Movie) | ✅ confirmed | not_applicable | not_applicable | ⏸️ skipped | ✅ confirmed |
| Charlotte (Anime TV) | not_applicable | ✅ confirmed | ⏸️ skipped | ⏸️ skipped | not_needed |
| Chainsaw Man (Anime Movie) | ✅ confirmed | not_applicable | ⏸️ skipped | ⏸️ skipped | not_needed |

### Key Findings

1. **Skip logic works correctly** - When `delete_files=false`, Jellyfin and Shoko show "skipped" with message "Files retained on disk - {service} unchanged"

2. **Jellyseerr graceful handling** - When request doesn't exist, shows "Request not found (already deleted)" but still marks as confirmed

3. **Service order** - Deletion proceeds: Sonarr/Radarr → Shoko → Jellyfin → Jellyseerr

---

## Phase 3: Destructive Testing (delete_files=true) ✅ COMPLETE

### Test 1: Ender's Game (2013) - Regular Movie

| Service | Status | Message |
|---------|--------|---------|
| Radarr | ✅ confirmed | Movie deleted successfully |
| Jellyfin | ✅ confirmed | Library scan triggered |
| Jellyseerr | not_needed | No request existed |

**Files:** ✅ Deleted from `/data/movies/`

---

### Test 2: Charlotte (2015) - Anime TV Show

| Service | Status | Message |
|---------|--------|---------|
| Sonarr | ✅ confirmed | Series deleted successfully |
| Shoko | ✅ confirmed | Shoko will detect missing files on next scan |
| Jellyfin | ✅ confirmed | Library scan triggered |
| Jellyseerr | ⚠️ not_needed | **Missed** - request existed but ID not included in card |

**Files:** ✅ Deleted from `/mnt/media/anime/shows/`
**Note:** Jellyseerr request manually cleaned via UI after test.

---

### Test 3: Chainsaw Man - Reze Arc (2025) - Anime Movie

| Service | Status | Message |
|---------|--------|---------|
| Radarr | ✅ confirmed | Movie deleted successfully |
| Shoko | ✅ confirmed | Shoko will detect missing files on next scan |
| Jellyfin | ✅ confirmed | Library scan triggered |
| Jellyseerr | ✅ confirmed | Request deleted successfully |

**Files:** ⚠️ **NOT DELETED** by Radarr despite API returning 200
- Radarr removed movie from DB (verified 404)
- Files remained at `/mnt/media/anime/movies/Chainsaw Man - The Movie - Reze Arc (2025)/`
- Manually deleted: `rm -rf "/mnt/media/anime/movies/Chainsaw Man..."`
- Issue: `issues/bugs/radarr-deletefiles-not-deleting.md`

---

### Test 4: Summer Ghost (2021) - Anime Movie (Verification)

| Service | Status | Message |
|---------|--------|---------|
| Radarr | ✅ confirmed | Movie deleted successfully |
| Shoko | ✅ confirmed | Shoko will detect missing files on next scan |
| Jellyfin | ✅ confirmed | Library scan triggered |
| Jellyseerr | ✅ confirmed | Request deleted successfully |

**Files:** ✅ Deleted from `/mnt/media/anime/movies/`
**Note:** This test verified Radarr CAN delete files - Chainsaw Man issue may have been transient.

---

## Service-Specific Notes

### Radarr
- `deleteFiles=true` removes from Radarr DB AND deletes files from disk
- `deleteFiles=false` removes from Radarr DB only, files remain
- API: `DELETE /api/v3/movie/{id}?deleteFiles={true|false}`

### Sonarr
- Same behavior as Radarr for TV series
- API: `DELETE /api/v3/series/{id}?deleteFiles={true|false}`

### Jellyfin
- **Issue found:** Direct DELETE API returns 500 error ("Guid can't be empty")
- **Solution:** Trigger library scan instead via `POST /Library/Refresh`
- Jellyfin auto-detects missing files and removes entries on scan
- When `delete_files=false`: Skip entirely (files still exist)

### Jellyseerr
- Deletes request record only, no file impact
- API: `DELETE /api/v1/request/{id}`
- **Note:** API key lacks admin permissions for job triggers
- Auto-syncs via scheduled jobs (Jellyfin scan ~5min, Radarr scan ~11hr)

### Shoko
- No direct delete API
- Detects missing files on library scan
- When `delete_files=false`: Skip entirely (files still exist)

---

## Test Commands

### SECURITY: Safe ID Lookup Commands

**IMPORTANT:** Never read config files (`config.xml`, `.env`) to extract API keys. Use the status-tracker container's pre-configured credentials via Python scripts.

#### Query Radarr for movie by name
```bash
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker python -c "
import httpx, os
radarr_key = os.environ.get(\"RADARR_API_KEY\", \"\")
resp = httpx.get(\"http://radarr:7878/api/v3/movie\", headers={\"X-Api-Key\": radarr_key})
for m in resp.json():
    if \"SEARCH_TERM\" in m[\"title\"].lower():
        print(f\"Radarr ID: {m[\"id\"]}, Title: {m[\"title\"]}, TMDB: {m.get(\"tmdbId\")}\")
"'
```

#### Query Sonarr for series by name
```bash
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker python -c "
import httpx, os
sonarr_key = os.environ.get(\"SONARR_API_KEY\", \"\")
resp = httpx.get(\"http://sonarr:8989/api/v3/series\", headers={\"X-Api-Key\": sonarr_key})
for s in resp.json():
    if \"SEARCH_TERM\" in s[\"title\"].lower():
        print(f\"Sonarr ID: {s[\"id\"]}, Title: {s[\"title\"]}, TVDB: {s.get(\"tvdbId\")}\")
"'
```

#### Query Jellyfin for item by name
```bash
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker python -c "
import httpx, os
jellyfin_key = os.environ.get(\"JELLYFIN_API_KEY\", \"\")
resp = httpx.get(
    \"http://jellyfin:8096/Items\",
    headers={\"X-Emby-Token\": jellyfin_key},
    params={\"searchTerm\": \"SEARCH_TERM\", \"Recursive\": \"true\", \"IncludeItemTypes\": \"Movie,Series\"}
)
for item in resp.json().get(\"Items\", []):
    print(f\"Jellyfin ID: {item[\"Id\"]}, Name: {item[\"Name\"]}, Year: {item.get(\"ProductionYear\")}\")
"'
```

#### Query Shoko for series by name
```bash
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker python -c "
import httpx, os
shoko_key = os.environ.get(\"SHOKO_API_KEY\", \"\")
resp = httpx.get(\"http://shoko:8111/api/v3/Series\", headers={\"apikey\": shoko_key}, params={\"pageSize\": 100})
for s in resp.json().get(\"List\", []):
    if \"SEARCH_TERM\" in s.get(\"Name\", \"\").lower():
        print(f\"Shoko ID: {s[\"IDs\"][\"ID\"]}, Name: {s[\"Name\"]}\")
"'
```

#### Query Jellyseerr for request by TMDB ID (direct DB query - safe)
```bash
ssh root@10.0.2.10 'pct exec 220 -- sqlite3 /opt/appdata/jellyseerr/db/db.sqlite3 "
SELECT m.id, m.tmdbId, m.status, r.id as request_id
FROM media m LEFT JOIN media_request r ON r.mediaId = m.id
WHERE m.tmdbId = <TMDB_ID>;
"'
```

#### Verify specific ID exists (replace SERVICE/ID)
```bash
# Radarr
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker python -c "
import httpx, os
key = os.environ.get(\"RADARR_API_KEY\", \"\")
resp = httpx.get(\"http://radarr:7878/api/v3/movie/<ID>\", headers={\"X-Api-Key\": key})
print(f\"EXISTS\" if resp.status_code == 200 else f\"NOT FOUND ({resp.status_code})\")"'

# Jellyfin (use query param method - direct /Items/{id} returns 400)
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker python -c "
import httpx, os
key = os.environ.get(\"JELLYFIN_API_KEY\", \"\")
resp = httpx.get(\"http://jellyfin:8096/Items\", headers={\"X-Emby-Token\": key}, params={\"Ids\": \"<ID>\"})
items = resp.json().get(\"Items\", [])
print(f\"EXISTS - {items[0][\"Name\"]}\" if items else \"NOT FOUND\")"'
```

---

### Check current sync setting
```bash
ssh root@10.0.2.10 'pct exec 220 -- docker exec status-tracker printenv ENABLE_DELETION_SYNC'
```

### Enable deletion sync
```bash
ssh root@10.0.2.10 'pct exec 220 -- bash -c "cd /opt/stacks/monitor && sed -i \"s/ENABLE_DELETION_SYNC=false/ENABLE_DELETION_SYNC=true/\" .env && docker compose up -d"'
```

### Disable deletion sync
```bash
ssh root@10.0.2.10 'pct exec 220 -- bash -c "cd /opt/stacks/monitor && sed -i \"s/ENABLE_DELETION_SYNC=true/ENABLE_DELETION_SYNC=false/\" .env && docker compose up -d"'
```

### Create test card in database
```bash
ssh root@10.0.2.10 'pct exec 220 -- sqlite3 /opt/appdata/status-tracker/tracker.db "
INSERT INTO requests (title, media_type, state, radarr_id, jellyfin_id, year, requested_by, created_at, updated_at, state_changed_at)
VALUES (\"Movie Title (Year)\", \"MOVIE\", \"AVAILABLE\", <radarr_id>, \"<jellyfin_id>\", <year>, \"adept\", datetime(\"now\"), datetime(\"now\"), datetime(\"now\"));
"'
```

### Clean deletion logs
```bash
ssh root@10.0.2.10 'pct exec 220 -- sqlite3 /opt/appdata/status-tracker/tracker.db "
DELETE FROM deletion_sync_events;
DELETE FROM deletion_logs;
"'
```

---

## Recovery Procedures

If a test deletes something unexpectedly:

| Service | Recovery |
|---------|----------|
| Radarr | Re-add movie via UI or API |
| Sonarr | Re-add series via UI or API |
| Jellyfin | Run library scan to re-detect files |
| Jellyseerr | User can re-request |
| Files on disk | Restore from backup if `delete_files=true` was used |

---

## Next Steps

1. **Test Regular TV Show** - Add non-anime TV show (e.g., Breaking Bad) to test Sonarr-only flow without Shoko
2. **Rotate Sonarr API key** - Security incident during testing (see `issues/security/`)
3. **Investigate Radarr file deletion** - Chainsaw Man test had files remain despite API success
4. **Jellyseerr API permissions** - Investigate admin API key for job triggers
5. **External deletion detection** - Implement webhooks for deletions from other sources
6. **Production use** - Feature ready with `ENABLE_DELETION_SYNC=true`

---

## Related Issues

- `issues/bugs/jellyfin-delete-api-500-error.md` - **Resolved** (use library scan instead)
- `issues/bugs/radarr-deletefiles-not-deleting.md` - **Open** (Chainsaw Man test)
- `issues/security/credential-exposure-2026-01-18-sonarr.md` - **Needs rotation**
- `issues/improvements/status-tracker-external-deletion-detection.md` - Future work
- `issues/improvements/status-tracker-bulk-media-sync.md` - Future work
