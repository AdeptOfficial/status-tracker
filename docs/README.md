# Status-Tracker Documentation

## Structure

```
docs/
├── reference/          # Useful reference docs
│   └── SHOKOFIN-VFS-REBUILD.md
└── archive/            # Historical (implemented/superseded)
    ├── planning/       # Original planning docs
    ├── flows/          # Phase implementation docs
    ├── sessions/       # Session handoff files
    └── features/       # Feature planning docs
```

See [Testing](TESTING.md) for the regression suite, browser tests and dev review.

## Quick Links

| Document | Description |
|----------|-------------|
| [../roadmap/](../roadmap/README.md) | **Start here** - Milestones; legacy internal plan in `roadmap/2026-10-20-internal-roadmap-legacy.md` |
| [SETUP.md](SETUP.md) | Project layout, network requirements, webhook configuration |
| [API.md](API.md) | Endpoints and authentication |
| [TROUBLESHOOTING.md](TROUBLESHOOTING.md) | Common issues, debug mode |
| [../ops/README.md](../ops/README.md) | Runbook: run, deploy, database, rollback |
| [reference/SHOKOFIN-VFS-REBUILD.md](reference/SHOKOFIN-VFS-REBUILD.md) | VFS rebuild commands and Shokofin config |

## Tracker

One file per item at the repo root: `bugs/` (malfunctions), `issues/` (gaps and
investigations), `features/` (ideas and accepted capabilities), `roadmap/`; each
folder's README is a generated index.

## Archive

Historical planning documents are in `archive/`. These were created during development and are kept for reference, but the work is complete.
