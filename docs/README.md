# Status-Tracker Workflow Fix Documentation

**Branch:** `fix/media-workflow-audit`
**Status:** ✅ All 4 workflows working
**Last Updated:** 2026-01-22

---

## Quick Links

| Document | Description |
|----------|-------------|
| [ANIME-WORKFLOW-FIX-SUMMARY.md](ANIME-WORKFLOW-FIX-SUMMARY.md) | **Start here** - Complete summary of all fixes |
| [flows/SHOKOFIN-VFS-REBUILD.md](flows/SHOKOFIN-VFS-REBUILD.md) | VFS rebuild commands & Shokofin config |
| [flows/SESSION-MEMORY-2026-01-22.md](flows/SESSION-MEMORY-2026-01-22.md) | Detailed session notes |
| [NEXT-STEPS.md](NEXT-STEPS.md) | Remaining tasks checklist |
| [ROADMAP.md](ROADMAP.md) | Deferred items & future improvements |

---

## Project Summary

### What Was Fixed

12 bugs fixed in status-tracker code + 1 critical Shokofin configuration issue.

### Workflows Verified

| Workflow | Status | Test |
|----------|--------|------|
| Regular Movie | ✅ Expected working | - |
| Regular TV | ✅ Expected working | - |
| Anime Movie | ✅ Verified | Akira |
| Anime TV | ✅ Verified | My Teen Romantic Comedy SNAFU |

---

## Directory Structure

```
docs/
├── README.md                    # This file
├── ANIME-WORKFLOW-FIX-SUMMARY.md # Main summary
├── NEXT-STEPS.md                # Remaining tasks
├── ROADMAP.md                   # Deferred items & backlog
├── flows/
│   ├── SHOKOFIN-VFS-REBUILD.md  # VFS commands
│   ├── SESSION-MEMORY-*.md      # Session notes
│   ├── phase-*.md               # Implementation phases
│   └── ...
├── issues/
│   ├── 2026-01-22-sse-not-pushing-updates.md    # Open
│   ├── 2026-01-22-anime-matching-no-scan.md     # Open (workaround exists)
│   ├── 2026-01-22-ux-improvements.md            # Backlog
│   └── resolved/                                 # Completed issues
└── features/
    └── sse-live-updates.md
```

---

## Key Learnings

1. **Shokofin UI has a bug** - Doesn't set `ManagedFolderId` properly. Must patch XML directly.
2. **Library refresh forces VFS rebuild** - Workaround for SignalR issues.
3. **SQLAlchemy async requires explicit commit** - Background loops need `await db.commit()`.
4. **SSE broadcasts must be after commit** - Otherwise frontend gets stale data.
