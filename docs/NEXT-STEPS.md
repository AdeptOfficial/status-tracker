# Next Steps Checklist

**Last Updated:** 2026-01-22

---

## Immediate (Before Merge)

- [x] **Rotate leaked API keys** (security) - DONE 2026-01-22
  - [x] Jellyfin API key - rotated
  - [x] Shoko API key - rotated

- [ ] **Test regular (non-anime) workflows**
  - [ ] Request a regular movie → verify flow to available
  - [ ] Request a regular TV show → verify flow to available

---

## Code Fixes (Optional Improvements)

- [ ] **SSE not pushing live updates** - `docs/issues/2026-01-22-sse-not-pushing-updates.md`
  - Dashboard shows "Live updates active" but requires manual refresh
  - Need to add logging to broadcaster to debug
  - Low priority - refresh works

- [ ] **ANIME_MATCHING doesn't trigger Jellyfin scan** - `docs/issues/2026-01-22-anime-matching-no-scan.md`
  - One-line fix in `jellyfin_verifier.py:440-445`
  - Change: `needs_scan = any(r.state in (RequestState.IMPORTING, RequestState.ANIME_MATCHING) for r in stuck_requests)`
  - Low priority - library refresh workaround exists

---

## UX Improvements (Backlog)

See `docs/issues/2026-01-22-ux-improvements.md` for full details.

- [ ] **SEARCHING state** - Add state between APPROVED and GRABBING
- [ ] **Episode progress** - Show "Grabbed 5/13" during GRABBING
- [ ] **Timeline "0 B" bug** - Shows "Downloading: 0 B" instead of size
- [ ] **Deletion sync** - Verify AniDB entries cleaned up on delete

---

## Infrastructure (Prod Deployment)

- [ ] **Mirror Shokofin config to prod**
  - Use `~/git/homeserver/configs/dev/services/jellyfin/README.md` as reference
  - Verify Shoko import folder IDs match
  - Patch Shokofin.xml with correct ManagedFolderId

- [ ] **Document prod library IDs**
  - Get library IDs: `curl -s -H 'X-Emby-Token: KEY' 'http://jellyfin:8096/Library/VirtualFolders' | jq`
  - Add to homeserver docs

---

## Merge Checklist

Before merging `fix/media-workflow-audit`:

- [ ] All 87 tests still pass
- [ ] API keys rotated
- [ ] Regular workflows tested
- [ ] Code deployed to dev and verified
- [ ] Documentation updated in homeserver repo

---

## Commands Reference

### Trigger VFS Rebuild
```bash
curl -X POST 'http://JELLYFIN:8096/Library/Refresh' -H 'X-Emby-Token: API_KEY'
```

### Check Request Status
```bash
curl -s 'http://localhost:8100/api/requests?page=1' | jq '.requests[] | {id, title, state}'
```

### Check Shokofin Config
```bash
docker exec jellyfin grep -A5 "ManagedFolderId" /config/plugins/configurations/Shokofin.xml
```
