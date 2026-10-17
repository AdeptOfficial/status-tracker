# Test suite broken: missing webhook fixtures + circular import

**Found:** 2026-10-17, during the AdepT branding pass (pre-existing — identical
results on the untouched tree).

## Symptoms

1. `./run_tests.sh` fails at docker build: it copies
   `docs/flows/captured-webhooks/` into the test image, but that directory no
   longer exists (docs/ is empty — likely lost in a reorg).
2. All `tests/test_flow_*.py` modules fail collection with a circular import:
   `app/services/__init__.py` → `deletion_orchestrator` → `app.clients.shoko`
   (`cannot import name 'shoko_http_client' from partially initialized module`).
3. Remaining suite (fixture-dependent tests skipped): 8 passed, 7 failed — the
   failures are `TestWebhookFixture` loads pointing at the same missing fixtures.

## Fix ideas

- Restore `docs/flows/captured-webhooks/` from git history
  (`git log --all --oneline -- docs/flows` to find the deleting commit) or
  re-capture webhook payloads from the live services.
- Break the services↔clients circular import (move `shoko_http_client` or defer
  the import inside the function that needs it).
- run_tests.sh should fail loudly if the fixtures dir is absent.

## Resolved 2026-10-17

- Fixtures weren't lost — the 2026-01-22 reorg (53632a2) moved them to
  `docs/archive/flows/captured-webhooks/`, stranding the tests' symlink. The six
  webhook JSONs now live as real files in `tests/fixtures/webhooks/` (test
  infrastructure, not archival docs); the dangling symlink and run_tests.sh's
  special COPY are gone.
- Circular import broken: `clients/shoko.py` now imports
  `verify_movie_by_tmdb` lazily inside the handler instead of at module level.
- 7 stale tests updated to current intended behavior: adaptive-polling tests
  assert `POLL_FAST`/`POLL_SLOW` constants (literals 5/30 predated the deliberate
  3/15 retuning); anime-matching tests now expect episodes to stay ANIME_MATCHING
  on a Shoko match with Jellyfin verification triggered (the verifier flips
  AVAILABLE, per the redesigned flow).
- Full suite: **87 passed, 0 failed** via `./run_tests.sh`.
