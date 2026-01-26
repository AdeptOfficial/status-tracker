# Issue: Timeline UX Improvements + Shoko Auto-Match Failure

**Date:** 2026-01-25
**Severity:** Low (UX polish)
**Status:** PENDING
**Type:** UI fix

---

## Problems

### 1. Inconsistent State Capitalization

The "downloaded" state displays in lowercase while all other states use Title Case:
- Approved ✓
- Grabbed ✓
- Downloading ✓
- downloaded ✗ (should be "Downloaded")
- Matching ✓

### 2. Raw Filename in "Matching" Timeline Entry

The Matching/Importing entry shows the full release filename:
```
Importing: [TekkenQ8] Spirited Away (2001) [BD 1080p] [Dub - Japanese, English, Arabic] [Sub - English, Arabic].mkv
```

This is not user-friendly. Should display something cleaner like:
- "Imported to library"
- "File imported: Spirited Away (2001)"
- Or just the movie title without the release group/codec details

## Expected Behavior

1. All timeline state names should use Title Case consistently
2. Timeline details should show clean, user-friendly text, not raw filenames

## Files to Check

- `app/templates/detail.html` - Timeline rendering
- `app/models.py` - State enum definitions (check display values)
- `app/plugins/radarr.py` - Webhook handler that sets the "Importing:" details

## Screenshot

Shows "downloaded" in lowercase and raw release filename in Matching entry.

---

## Additional Issue: Shoko Auto-Match Failure

During testing, "Spirited Away" file was not auto-matched by Shoko:
```
FileNotMatched: AutoMatchAttempts=1, HasCrossReferences=False
```

**Impact:** Request stuck at `anime_matching` state indefinitely until manual match in Shoko.

**Possible improvements:**
1. Add UI indicator when Shoko can't auto-match (shows "Waiting for manual match")
2. Link to Shoko unrecognized files page from status-tracker
3. Add timeout/alert if stuck in anime_matching for too long
