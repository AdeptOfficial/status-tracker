# Episode counter exceeds total (e.g. "47/22 ready")

Seen on prod /history (2026-10-17): Assassination Classroom S02 card shows
"EPISODES 47/22 ready" — grabbed/available episode rows exceed total_episodes.
Likely multi-season or re-grab rows counted against a single season's total
(total_episodes=22 but 47 Episode rows attached to the request).

Repro: open /history, card "Assassination Classroom (2015 · S02)".
Check: episode rows per request vs total_episodes; dedupe by (season, episode)?

## Resolved 2026-10-17

Root cause (prod data): the S02 request (total_episodes=22) carried 47 episode
rows spanning S01+S02 — the correlator attaches whole-series webhook events to
a single-season request. Display now scopes to the request's season via
`season_episodes()` (state_calculator, exposed to Jinja), used by both
card.html and detail.html for counts, bars, and the episode list; the total is
`max(total_episodes, season rows)` so drift (25 S02 rows vs 22 metadata) can
never exceed 100%. 4 regression tests added; 91/91 passing.
Note: the ingestion-side question (should S01 rows attach at all?) is left as
is — display-only fix, aggregation behavior unchanged.
