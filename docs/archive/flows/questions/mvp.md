# MVP Questions

## Open

### Q7: Shoko FileMatched - how do we receive it?

Acceptance says:
> Shoko FileMatched → AVAILABLE

How do we listen to Shoko events?
- A) Shoko webhook (does Shoko have webhooks?)
- B) Shoko SignalR connection
- C) Poll Shoko API
- D) Shoko plugin sends to us

**Status:** INVESTIGATE

### Q8: Fallback checker timing

How long before fallback kicks in? What interval?
- A) Check every 30 seconds for requests stuck > 5 minutes
- B) Check every 1 minute for requests stuck > 10 minutes
- C) Configurable?

**Status:** INVESTIGATE - Need to determine appropriate timing

---

## Answered

### Q1: GRABBING state - in or out?

**Decision:** A - GRABBING is in MVP, with episode count display ("Grabbed 3/12 eps").

### Q2: Download progress % - in or out?

**Decision:** A - Download progress % is in MVP. Show percentage during DOWNLOADING state.

### Q3: INDEXED vs GRABBING state

**Decision:** INDEXED state removed. Use GRABBING for TV shows. Movies skip directly to DOWNLOADING.

### Q4: Duplicate request - what does "returns existing" mean?

**Decision:** B - **Redirect to existing request**. UI navigates user to the in-progress request page.

### Q5: Test scenarios vs state machine inconsistency

**Decision:** Update test scenarios to use GRABBING (INDEXED is outdated terminology).

### Q6: Database schema - which is authoritative?

**Decision:** `database.md` is the source of truth. `MVP.md` shows simplified view for scope definition.

---

## Follow-up Questions

### Q9: Download progress % - per-episode or aggregate?

Q2 says show download progress %. For TV with multiple downloads:
- A) Show aggregate progress across all episodes (sum bytes / sum total)
- B) Show per-episode progress in expanded view ✓
- C) Both

**Decision:** B - Two-level display:
- **List view (compact):** "4/13 eps" - count of completed episodes
- **Detail view (expanded):** Per-episode progress "Ep 3 at 68%"

### Q10: qBit polling frequency

Download progress requires qBit polling. How often?
- A) Every 5 seconds (responsive but chatty)
- B) Every 15 seconds (balance)
- C) Every 30 seconds (less load)
- D) Adaptive (fast when active, slow when idle) ✓

**Decision:** D - Adaptive polling. Fast (5s) when downloads active, slow (30s) when idle.

### Q11: MVP.md needs update

Several decisions invalidate parts of MVP.md:
- INDEXED state removed (use GRABBING)
- Episode table added (per-episode tracking)
- State machine diagram outdated

**Decision:** Update after all questions resolved. Added to todo list.
