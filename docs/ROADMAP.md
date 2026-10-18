# Status-Tracker Roadmap

**Last Reviewed:** 2026-10-17 (validation update; historical backlog below)

Single source of truth for priorities, backlog, and deferred items.

---

## Next task — automatic anime library refresh

See the [October18 handoff](../issues/2026-01-22-anime-matching-no-scan.md).
Investigate the current trigger before implementing coalesced refresh, bounded
retries and explicit waiting feedback. Require unattended DEV recovery tests;
manual scan recovery and successful playback do not establish automation reliability.
User requested documentation only at tonight's wrap-up. Production remains on hold.

## Current iteration — episode progress and library repair

Downloaded/ready summaries, conservative per-file percentages and permanent tests
are implemented and dev-deployed. [Testing](TESTING.md) records 152 passing
regressions, browser acceptance and review instructions. Desktop visual review approved; real-content mobile overflow is fixed and verified
at five viewport widths on dev. Real request 20 has downloaded/imported all 12 episodes; matching completed, a manual Jellyfin scan recovered availability, and user playback passed. Automatic refresh remains unverified. Production is explicitly on hold.
The historical priorities below predate this iteration; do not reimplement these
completed pieces from unchecked January boxes.

Library-sync repair and separate History source/user filters are implemented.
DEV History and repair-label visual review approved. Import-completion labels
are now explicit; production remains on hold.

## October 17 validation update

- Current suite: 91 tests pass in an isolated container; async cleanup and
  deprecation warnings remain recorded in the SSE issue.
- Direct dev SSE remained connected for 45 seconds with heartbeats.
- Isolated Firefox detail-page checks pass progress/speed/ETA/timeline updates,
  server-restart reconnection and Ready to Watch status without page reload.
- No current browser bug reproduced in that path. Real download-pipeline and
  proxy-path verification remain distinct; do not assume old open reports are
  newly reproduced. See [browser evidence](../issues/detail-page-live-updates-bug.md).

## Current Priorities

Work on these in order:

| Priority | Task | Issue/Notes |
|----------|------|-------------|
| 1 | **Test SSE heartbeat stability** | Should stay connected >15s now. `issues/sse-connections-dropping.md` |
| 2 | **Import timeline visibility — fixed on DEV** | Import-complete events say Imported; current Matching state retained. `issues/2026-01-22-importing-state-skipped-for-anime.md` |
| 3 | **Episode progress UI** | Show "x downloaded, y ready" not just "x ready". `issues/ui-episode-progress-improvements.md` |
| 4 | **Library sync: populate missing IDs** | Sync button should fill missing jellyfin_id, tvdb_id, etc. `issues/library-sync-should-populate-missing-ids.md` |

---

## Current Working State

**As of 2026-01-22:**

| Feature | Status |
|---------|--------|
| SSE live updates | ✅ Working (heartbeat added) |
| Anime movies | ✅ Full flow working |
| Anime TV shows | ✅ Full flow working (tested with Bocchi) |
| Jellyfin fallback checker | ✅ Polls every 30s |
| Episode handling in webhooks | ✅ Fixed (Jellyseerr + Jellyfin) |
| History page | ✅ Fixed (selectinload) |
| Timeline labels | ✅ Fixed ("Grabbed" not "grabbing") |

---

## Blocked Items

### Regular (Non-Anime) Workflow Testing

**Status:** Blocked - Indexers not working
**Priority:** Medium

**Tasks when unblocked:**
- [ ] Request a regular movie → verify flow to AVAILABLE
- [ ] Request a regular TV show → verify flow to AVAILABLE
- [ ] Document any differences from anime workflows

---

## Backlog

### UI Improvements

| Item | Priority | Issue |
|------|----------|-------|
| Per-episode download % | Low | `issues/ui-episode-progress-improvements.md` |
| Remove "Matching" label for anime | Low | Shows "Downloaded" instead |
| New SEARCHING state | Low | Between APPROVED and GRABBING |
| Timeline "0 B" display bug | Low | Shows "Downloading: 0 B" in some cases |

### Code Improvements

| Item | Priority | Issue |
|------|----------|-------|
| ANIME_MATCHING trigger scan | Low | One-line fix in `jellyfin_verifier.py`. `docs/issues/2026-01-22-anime-matching-no-scan.md` |
| Delete integration gaps | Medium | `issues/deletion-integration-gaps.md` |
| External deletion detection | Low | `issues/status-tracker-external-deletion-detection.md` |

### Infrastructure

| Item | Priority | Notes |
|------|----------|-------|
| Mirror Shokofin config to prod | High (before prod) | Get library IDs, patch ManagedFolderId |
| Document prod library IDs | Medium | Add to homeserver docs |

---

## Merge Checklist

Before merging `feature/per-episode-tracking`:

- [x] SSE heartbeat fix
- [x] Grabbed label fix
- [x] History page 500 fix
- [x] Episode state handling fix (Jellyseerr + Jellyfin)
- [x] API keys rotated
- [ ] Regular workflows tested
- [ ] All tests still pass
- [ ] Code deployed to dev and verified

---

## Commands Reference

### Deploy to Dev
```bash
rsync -avz --exclude '.env' --exclude '__pycache__' --exclude '.git' \
  /home/adept/git/status-tracker-workflow-fix/ root@10.0.2.10:/tmp/status-tracker-update/

ssh root@10.0.2.10 "cd /tmp/status-tracker-update && tar --exclude='.env' -cf - . | pct exec 220 -- tar -xf - -C /opt/status-tracker/"

ssh root@10.0.2.10 "pct exec 220 -- bash -c 'cd /opt/status-tracker && docker compose up -d --build'"
```

### Check Health
```bash
ssh root@10.0.2.10 "pct exec 220 -- curl -s http://localhost:8100/api/health"
```

### Trigger VFS Rebuild
```bash
curl -X POST 'http://JELLYFIN:8096/Library/Refresh' -H 'X-Emby-Token: API_KEY'
```

---

## Completed

- [x] All 4 workflows tested and working (2026-01-22)
- [x] 12+ code fixes deployed
- [x] Shokofin ManagedFolderId fix documented
- [x] SSE heartbeat fix (15s keepalive)
- [x] Grabbed label fix (timeline past tense)
- [x] History page 500 fix (selectinload)
- [x] Jellyseerr MEDIA_AVAILABLE fix (episodes + jellyfin_id)
- [x] Jellyfin ItemAdded fix (episodes marked AVAILABLE)
- [x] Bocchi the Rock full test (12/12 episodes)
