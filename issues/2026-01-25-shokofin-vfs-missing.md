# Issue: Shokofin VFS Directories Missing - Jellyfin Can't Index Anime

**Date:** 2026-01-25
**Priority:** Medium
**Status:** Manual Fix Applied (needs proper automation)

## Problem

Jellyfin anime libraries are configured to use Shokofin's VFS (Virtual File System), but the VFS directories were missing:

```
/config/Shokofin/VFS/29391378-c411-8b35-b77f-84980d25f0a6  (Anime Shows) - MISSING
/config/Shokofin/VFS/3e840160-b2d8-a553-d882-13a62925f0fa  (TV-Shows) - MISSING
/config/Shokofin/VFS/abebc196-cc1b-8bbf-6f8b-b5ca7b5ad6f1  (Anime Movies) - EXISTS
```

This caused:
- Jellyfin couldn't find anime series even after files were imported
- Status-tracker fallback verification couldn't transition to AVAILABLE
- Library scans showed "path does not exist" errors

## Manual Fix Applied

```bash
# Create VFS directories
mkdir -p /opt/appdata/jellyfin/Shokofin/VFS/29391378-c411-8b35-b77f-84980d25f0a6
mkdir -p /opt/appdata/jellyfin/Shokofin/VFS/3e840160-b2d8-a553-d882-13a62925f0fa

# Symlink anime shows content
cd /opt/appdata/jellyfin/Shokofin/VFS/29391378-c411-8b35-b77f-84980d25f0a6
ln -s /mnt/media/anime/shows/* ./
```

## Root Cause Investigation Needed

Why didn't Shokofin generate VFS for these libraries?
- Shokofin v6.0.2.0 is installed
- Plugin is configured with correct Shoko host/API key
- `/Shokofin/VFS/Generate` endpoint was called but didn't create directories

Possible causes:
1. Library not properly linked to Shoko in Shokofin settings
2. VFS generation only works for newly added series
3. Manual VFS generation requires specific parameters

## Recommended Actions

### Short Term (Status-Tracker)
Add Jellyfin VFS health check to fallback verifier:
```python
# In jellyfin_verifier.py check_stuck_requests_fallback()
# Log warning if VFS paths don't exist for anime libraries
```

### Long Term (Infrastructure)
1. Document Shokofin VFS setup requirements
2. Add VFS directory verification to media stack startup
3. Consider switching to direct library paths if VFS continues to be unreliable

## Jellyfin Library Configuration

| Library | ItemId | VFS Path | Status |
|---------|--------|----------|--------|
| TV-Shows | 3e840160... | `/config/Shokofin/VFS/3e840160-...` | Fixed manually |
| Anime Shows | 29391378... | `/config/Shokofin/VFS/29391378-...` | Fixed manually |
| Anime Movies | abebc196... | `/config/Shokofin/VFS/abebc196-...` | Was working |
| Movies | f137a2dd... | `/data/movies` | Direct path |

## Related

- Shokofin plugin config: `/opt/appdata/jellyfin/plugins/configurations/Shokofin.xml`
- Jellyfin logs showed: `DirectoryNotFoundException` for VFS paths
