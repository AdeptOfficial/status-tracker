# Duplicate movie caused by conflicting provider IDs

Status: repaired and verified on DEV, 2026-10-17. Production untouched.

## Evidence

The original 2007 movie request (2) used TMDB `38142` / IMDb `tt0983213`,
but imported record 3 used Jellyfin's TMDB `1359916`. Jellyfin also reported
IMDb `tt33477484` while retaining the 2007 title/year. Radarr movie 61 and
Shoko series 28 both agreed on the original request's IDs. Jellyfin's Shokofin
virtual path resolved to the exact same physical movie file managed by Radarr.
This was a metadata mismatch, not two media files or a newly created sync duplicate.
The provider/refresh that originally introduced the mismatch is not established.

## Repair

- Backed up tracker SQLite and the original Jellyfin item metadata.
- Corrected only Jellyfin's TMDB/IMDb IDs and set `LockData=true` for this item
  to prevent automatic metadata replacement. This locks metadata updates for
  this movie; future intentional metadata refreshes may require unlocking it.
- Linked original request 2 to the verified Jellyfin item and Shoko series 28.
- Moved the import timeline event to request 2 before removing redundant record 3.
  Preserved all six original events and added one explicit repair audit event.
- Kept original request title, requester, service IDs, status and other metadata.
  No service deletion APIs were called; no media files were changed or deleted.
- No generic title-based merging or changes to conservative sync matching.

## Verification

Two live DEV syncs each returned 10 scanned, 0 added, 0 updated, 10 already
tracked, 0 errors. Jellyfin's scan reached Idle and corrected IDs/lock persisted.
History now has 10 requests and zero separate library imports. All original
timeline event contents and all unrelated requests/episodes match the backup.
SQLite integrity and foreign-key checks pass. Existing application suite remains
134 tests; this was a targeted data repair, not a runtime-code release.

Rollback evidence and visual checks are in the homeserver DEV service record.
Do not restore the entire backup over subsequent writes. Record 3 is retired;
use `/request/2` for the movie and its combined history.
