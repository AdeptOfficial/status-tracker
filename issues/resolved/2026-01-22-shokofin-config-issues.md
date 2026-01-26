# Issue: Shokofin Configuration Limitations

**Date:** 2026-01-22
**Type:** Infrastructure (Shokofin/Jellyfin, not status-tracker)
**Status:** ✅ RESOLVED

---

## Issues Found

### 1. SignalR Was Disabled
- **Impact:** VFS never regenerated after Shoko matched files
- **Fix:** Enable SignalR in Shokofin Connection settings
- **Status:** Fixed

### 2. Anime Shows Library Not Configured in Shokofin
- **Problem:** Shokofin config only has Anime Movies and TV-Shows, missing Anime Shows
- **Evidence:** `Shokofin.xml` contains:
  - `abebc196-cc1b-8bbf-6f8b-b5ca7b5ad6f1` - Anime Movies ✓
  - `3e840160-b2d8-a553-d882-13a62925f0fa` - TV-Shows (stale/missing VFS dir)
  - **Missing:** `29391378-c411-8b35-b77f-84980d25f0a6` - Anime Shows
- **Impact:** VFS never generates for Anime Shows, anime TV stuck at `anime_matching`
- **Status:** Open - need to add Anime Shows library to Shokofin config via UI

### 3. UI Limitation - Multi-Library Selection
- **Problem:** Shokofin UI doesn't allow selecting both "Anime Shows" and "Anime Movies" in library picker
- **Impact:** Must configure libraries one at a time
- **Status:** Open - may need to edit XML directly or use API

---

## Recommendations

1. Check Shokofin documentation for multi-library setup
2. Ask on Shoko Discord if this is expected behavior
3. Consider if VFS mode is necessary, or if "Legacy Filtering" works better for this setup

---

## Impact on Status-Tracker Testing

These Shokofin issues block the anime workflow testing. Status-tracker code appears correct, but cannot verify end-to-end flow until Shokofin is properly configured.

**Workaround for testing:** Focus on non-anime content, or anime movies only (whichever library is configured).
