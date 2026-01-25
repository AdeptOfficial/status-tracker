# Bug: Download Size Shows "0 B" Instead of Actual Size

**Created:** 2026-01-25
**Status:** Open
**Priority:** Medium
**Category:** UI / Data

## Problem

Timeline event for downloading state shows "Downloading: 0 B" instead of the actual file size.

## Screenshot Evidence

- Timeline shows: "Downloading: 0 B"
- But download is clearly in progress (8.4% shown, 29.1 MB/s speed)

## Expected Behavior

Should show actual torrent size, e.g., "Downloading: 2.5 GB"

## Possible Cause

1. Size not being extracted from qBittorrent webhook/polling
2. Size field not being stored in timeline event details
3. Format string using wrong field

## Files to Investigate

- `app/plugins/qbittorrent.py` - Where download details are set
- `app/services/qbittorrent_poller.py` - Polling logic
- Check how `details` string is built for downloading state
