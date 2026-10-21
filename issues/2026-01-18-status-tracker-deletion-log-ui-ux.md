# Status Tracker: Deletion Log UI/UX Improvements

**Created:** 2026-01-18
**Status:** In Progress
**Component:** apps/status-tracker

## Summary

Multiple UI/UX issues identified in the deletion logs feature during testing. These affect usability and data accuracy.

---

## Issue 1: Duplicate Deletion Logs

**Current behavior:** Each deletion creates multiple log entries as status changes (e.g., one "In Progress" row, then another "Complete" row for the same deletion).

**Expected behavior:** ONE log per deletion that updates in-place:
- Row starts as "In Progress"
- Same row updates to "Complete" (or "Incomplete" if errors)
- Never create multiple log rows for the same deletion operation

**Root cause:** Creating new DeletionLog entries on status updates instead of updating the existing one.

**Files affected:**
- `app/services/deletion_orchestrator.py`
- `app/models.py` (may need status field on DeletionLog)

---

## Issue 2: Missing Services in Sync Timeline

**Current behavior:** Only shows services that have sync events recorded (e.g., just Radarr and Jellyseerr).

**Expected behavior:** Show ALL possible services in the timeline:
- **Sonarr** (for TV) or **Radarr** (for movies)
- **Shoko** (for anime)
- **Jellyfin**
- **Jellyseerr**

Services not applicable should show as "N/A" or "Not applicable" (e.g., Sonarr for a movie, Shoko for non-anime).

**Files affected:**
- `app/templates/deletion-logs.html` (or modal template)
- `app/services/deletion_orchestrator.py` (ensure all services get events)

---

## Issue 3: Completion Status Logic

**Current behavior:** Status shows "Complete" even when services are just "skipped".

**Expected behavior:**
- **Complete** = ALL services returned success (confirmed/verified) OR were appropriately skipped
- **Incomplete** = ANY service has errors (failed status)
- User can click Details to see exactly which service failed

**Files affected:**
- `app/services/deletion_orchestrator.py` (`_check_completion` method)
- `app/models.py` (may need `DeletionStatus` enum)

---

## Issue 4: "Deleted by" Shows Test Value

**Current behavior:** Shows "dry-run-test" (hardcoded test value from testing).

**Expected behavior:**
- **Dashboard deletion by admin:** Show actual Jellyfin username (e.g., "adept")
- **System/external deletion:** Show "System" (when detected via webhook)
- **Agent/automation deletion:** Show "Automation" or identifier

**Root cause:** The `username` parameter passed to `delete_request()` during testing was hardcoded. Should come from authenticated Jellyfin user.

**Files affected:**
- `app/routers/api.py` (ensure auth user info is passed correctly)
- `app/services/auth.py` (verify username extraction)

---

## Issue 5: Year Shows "N/A"

**Current behavior:** Year shows "N/A" even though title contains "(2013)".

**Expected behavior:** Should display the actual year (e.g., "2013").

**Root cause:** The `year` field on MediaRequest isn't being populated when the request is created (missing from Jellyseerr webhook parsing). DeletionLog then snapshots `None`.

**Fix options:**
1. Fix Jellyseerr plugin to extract year from webhook payload
2. Parse year from title as fallback (regex: `\((\d{4})\)`)

**Files affected:**
- `app/plugins/jellyseerr.py` (webhook parsing)
- `app/services/deletion_orchestrator.py` (fallback parsing)

---

## Acceptance Criteria

- [ ] Single log entry per deletion (updates in-place)
- [ ] All 4-5 services shown in Sync Timeline with appropriate status
- [ ] "Complete" only when no failures; "Incomplete" if any failed
- [ ] "Deleted by" shows actual Jellyfin username or "System"
- [ ] Year displays correctly (from data or parsed from title)

---

## Related Files

- Plan: `~/.claude/plans/dynamic-riding-minsky.md`
- DIARY: `apps/status-tracker/DIARY.md`
- README: `apps/status-tracker/README.md`
