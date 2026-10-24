# Split anime sequel verification — resolved on DEV

S2 imports can be presented as S1 of a separate Jellyfin sequel series with reused
parent TMDB/TVDB IDs. The old verifier returned the first series and required
identical season numbers, leaving ten actually available episodes in Matching.

Verifier now maps each imported path to an unambiguous confirmed Shoko file,
then to exact playable Jellyfin episode evidence across series. It retains the
requested season labels and uses the actual sequel series for Watch. Duplicate
or shared files, conflicting series, missing paths/API evidence and cached Ready
flags cannot prove completion. Requests without Shoko import paths keep existing
number-based verification. Combined episode files need separate handling; do not
guess their identity. No title/ordinal offset or per-show hardcoded IDs.

240 regressions and full Firefox suite pass. DEV tracker22 reached Available10/10
at2026-10-20T16:50:36.520443Z via normal fallback after deploying split-files image.
All ten Shoko source IDs345–354 matched/readable in Jellyfin. S1 preserved; actual
S2 Watch link, both season detail pages/SSE/five viewports pass. No manual scan,
status update or retry-budget reset. Runtime/source hashes verified.

Jellyseerr S2 availability is a separate unresolved scanner/provider-precedence
issue; see homeserver issues/bugs/dev-jellyseerr-split-anime-season-availability.md.
Interstellar's delayed synchronization completed normally. Production unchanged.
