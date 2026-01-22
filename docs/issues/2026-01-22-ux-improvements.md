# UX Improvements Identified

**Date:** 2026-01-22
**Source:** Live testing session

---

## 1. Missing SEARCHING State

**Problem:** After APPROVED, there's a gap before GRABBING where the user doesn't know what's happening.

**Current flow:**
```
APPROVED → (waiting...) → GRABBING
```

**Proposed flow:**
```
APPROVED → SEARCHING → GRABBING
```

**Implementation notes:**
- Trigger SEARCHING when Jellyseerr sends approval (or Sonarr confirms series added)
- Transition to GRABBING when Sonarr sends Grab webhook
- Helps user understand the system is actively working

---

## 2. Episode Progress Display

**Problem:** During GRABBING state for TV shows, should display "Grabbed 5/13" style progress.

**Current:** Just shows "Grabbing" with no episode count

**Proposed:** "Grabbing (5/13 episodes)" or similar

**Implementation notes:**
- Episodes are created on first Grab webhook
- Count episodes with state >= GRABBING vs total episodes
- Display in UI timeline or status badge

---

---

## 3. Season Pack Mismatch (Sonarr Issue)

**Problem:** User requests Season 1 only, but Sonarr grabs a season pack with S1+S2+OVA. Neither Sonarr nor status-tracker realizes the extra content.

**Example:**
- Requested: My Teen Romantic Comedy SNAFU Season 1 (13 episodes)
- Grabbed: S1+S2+OVA pack (actual content)
- Sonarr shows: Season 1: 13/13 (14.3 GiB) - doesn't recognize extra seasons
- Status-tracker: Only tracks what Sonarr reports

**Root Cause:**
- Release naming doesn't match Sonarr's parsing expectations
- Sonarr imports all files but only tracks Season 1 episodes
- Extra content (S2, OVAs) imported but untracked

**Impact:**
- Episode count mismatch
- Extra content exists on disk but not in Sonarr/status-tracker
- Shoko may match all files, causing confusion

**Note:** This is primarily a Sonarr/release naming issue, not status-tracker

---

---

## 4. Timeline Shows "Downloading: 0 B"

**Problem:** Timeline entry for "Downloading" shows "0 B" instead of current progress/size.

**Screenshot:** Spirited Away test - header shows 381.7 KB/s, ETA 7d 3h, but timeline shows "Downloading: 0 B"

**Expected:** Timeline should show file size or update with progress

**Location:** Likely in timeline entry creation (qbittorrent plugin or frontend display)

---

## 5. Deletion Sync with AniDB/Shoko

**Problem:** When anime content is deleted, the AniDB entry in Shoko should also be cleaned up.

**Expected behavior:** Deleting media should remove:
- Files from disk
- Entries from Sonarr/Radarr
- Entries from Shoko (including AniDB linkage)

**Current behavior:** Unclear if Shoko entries are cleaned up when media is deleted via status-tracker.

**Investigation needed:**
- Does status-tracker's delete trigger Sonarr/Radarr deletion?
- Does Sonarr/Radarr deletion trigger Shoko cleanup?
- Is this expected Shoko behavior or a config issue?

---

## Priority

- [ ] SEARCHING state - Medium (UX clarity)
- [ ] Episode progress - Medium (UX clarity)
- [ ] Deletion sync - Medium (data hygiene)
- [ ] Season pack mismatch - Low (edge case)
- [ ] Timeline "0 B" display - Low (cosmetic)
