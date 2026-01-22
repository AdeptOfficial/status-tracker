# Status-Tracker Roadmap

**Last Updated:** 2026-01-22

---

## Deferred Items

### Regular (Non-Anime) Workflow Testing

**Status:** Blocked - Indexers not working
**Priority:** Medium
**Blocked By:** Indexer infrastructure issues

**Tasks when unblocked:**
- [ ] Request a regular movie → verify flow to `available`
- [ ] Request a regular TV show → verify flow to `available`
- [ ] Document any differences from anime workflows

**Notes:** The anime workflows have been fully tested and verified. Regular workflows share most of the same code paths but use Radarr/Sonarr directly without Shoko integration. Expected to work but needs verification.

---

## Optional Improvements

### SSE Live Updates Not Working

**Status:** Open
**Priority:** Low
**Issue:** `docs/issues/2026-01-22-sse-not-pushing-updates.md`

Dashboard shows "Live updates active" but requires manual refresh to see state changes.

**Investigation needed:**
- [ ] Add logging to SSE broadcaster
- [ ] Check browser console for connection issues
- [ ] Verify EventSource connection stays open

**Workaround:** Manual page refresh works fine.

---

### ANIME_MATCHING State Doesn't Trigger Jellyfin Scan

**Status:** Open (workaround exists)
**Priority:** Low
**Issue:** `docs/issues/2026-01-22-anime-matching-no-scan.md`

Fallback checker triggers Jellyfin library scan for `IMPORTING` state but not `ANIME_MATCHING`.

**Fix (one-line):**
```python
# jellyfin_verifier.py:440-445
# Change:
needs_scan = any(r.state == RequestState.IMPORTING for r in stuck_requests)
# To:
needs_scan = any(r.state in (RequestState.IMPORTING, RequestState.ANIME_MATCHING) for r in stuck_requests)
```

**Workaround:** Manual library refresh via API forces VFS rebuild.

---

## UX Improvements Backlog

### SEARCHING State

**Priority:** Low

Add intermediate state between `APPROVED` and `GRABBING` to show when Sonarr/Radarr is searching for releases.

**Current flow:** APPROVED → GRABBING
**Proposed flow:** APPROVED → SEARCHING → GRABBING

---

### Episode Progress Display

**Priority:** Low

Show progress during grabbing/importing for TV shows: "Grabbed 5/13 episodes"

Currently shows generic "Grabbing" without progress indication.

---

### Timeline "0 B" Display Bug

**Priority:** Low

Timeline shows "Downloading: 0 B" instead of actual file size in some cases.

**Investigation needed:** Check where download size is populated in webhook handlers.

---

### Deletion Sync with AniDB

**Priority:** Medium

Verify that when media is deleted:
1. Jellyfin removes from library
2. Shoko removes from database
3. AniDB watch status is cleaned up (if applicable)

**Notes:** Need to clarify expected behavior - should AniDB entries be removed on delete?

---

## Infrastructure (Production Deployment)

### Mirror Shokofin Config to Production

**Priority:** High (before prod deployment)

**Tasks:**
- [ ] Get Shoko import folder IDs on prod server
- [ ] Get Jellyfin library IDs on prod server
- [ ] Patch Shokofin.xml with correct `ManagedFolderId` values
- [ ] Trigger library refresh to rebuild VFS
- [ ] Verify anime appears in Jellyfin

**Reference:** `~/git/homeserver/configs/dev/services/jellyfin/README.md`

---

### Document Production Library IDs

**Priority:** Medium

```bash
# Get library IDs
curl -s -H 'X-Emby-Token: KEY' 'http://jellyfin:8096/Library/VirtualFolders' | jq '.[] | {Name, ItemId}'
```

Add to homeserver docs for reference.

---

## Completed

- [x] All 4 workflows tested and working (2026-01-22)
- [x] 12 code fixes deployed
- [x] Shokofin ManagedFolderId fix documented
- [x] 87 tests passing
