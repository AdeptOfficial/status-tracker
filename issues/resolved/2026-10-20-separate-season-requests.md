# Separate season requests and related-season UI

Status: Resolved and verified on DEV, 2026-10-20. Production remains on hold.

Separate Cyberpunk Jellyseerr requests150/S2 and151/S1 were correlated by shared
show IDs. Sonarr's S1 Grab overwrote the single tracker row's season while the
row still retained request150 and requested_seasons=2.

New TV request IDs now remain distinct; Sonarr uses season-aware correlation and
ambiguous show-only matches are rejected. TV availability notifications invoke
per-episode verification. Active cards show sibling season states; detail pages
link to each season's own episode progress and timeline.

A backed-up DEV repair preserved tracker21's ten S1 episode rows and history,
assigned Jellyseerr151, and restored S2 as tracker22/Jellyseerr150 Approved. Audit
events explain the historical mixed identity. No request replay or redownload.

Regression coverage: `tests/test_season_identity.py`; permanent Firefox suite.
Actual home and both details pass at320/390/768/1440/2048px with SSE. S1 reached
Ready10/10 automatically and user confirmed S1E1 playback; S2 stayed Approved.

Not established: S2's eventual provider mapping, a single Jellyseerr request
selecting several seasons, or season-scoped deletion/re-request behavior. Keep
these explicit in the roadmap rather than extrapolating from the S1 result.
