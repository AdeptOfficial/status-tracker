# Issue: Sonarr Webhook Not Configured

**Date:** 2026-01-22
**Severity:** High
**Status:** Resolved (manual fix)

---

## Problem

Request "My Teen Romantic Comedy SNAFU" stuck at `APPROVED` state despite Sonarr actively grabbing episodes (reached ep 9).

## Root Cause

Sonarr webhook was not configured to send to status-tracker. The connection existed but either:
- Was pointing to jellyseerr instead of status-tracker
- Was not saved/active when grabs started

## Impact

- Request stayed at `APPROVED` indefinitely
- No episode tracking (0 episodes created)
- `is_anime` remained `null` (set by Sonarr grab handler)
- Users see no progress despite active downloads

## Resolution

Configure Sonarr webhook:
- **URL:** `http://status-tracker:8000/hooks/sonarr`
- **Events:** On Grab, On File Import, On Import Complete
- Click **Test** to verify, then **Save**

## Prevention

Add deployment checklist item:
- [ ] Verify Sonarr webhook points to status-tracker
- [ ] Verify Radarr webhook points to status-tracker
- [ ] Test each webhook connection after deployment

## Related

This also surfaces the need for a `SEARCHING` state between `APPROVED` and `GRABBING` - see `2026-01-22-ux-improvements.md`
