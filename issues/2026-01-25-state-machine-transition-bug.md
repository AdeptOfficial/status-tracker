# Critical Bug: State Machine Blocks downloading -> anime_matching Transition

**Date:** 2026-01-25
**Status:** Open
**Severity:** Critical (blocks automation)
**Request ID:** 10 (My Tiny Senpai)

## Description

Request stuck in `downloading` state despite:
- Download 100% complete (Bluray pack)
- All 12 episodes imported by Sonarr
- Shoko matched all 12 files via SignalR
- Episodes in DB show `anime_matching` state

The state machine rejects the transition, logging:
```
Invalid transition for request 10: downloading -> anime_matching
```

## Root Causes

### 1. Missing qbit_hash Association
- Sonarr Grab webhook didn't set `qbit_hash` on the request
- Progress tracking failed (showed 0% despite actual progress)
- Fallback loop queries require `qbit_hash IS NOT NULL`

### 2. Missing Import State Transition
- Sonarr Import webhook either didn't fire or wasn't processed
- Expected: `downloading -> downloaded -> importing -> anime_matching`
- Actual: Stayed in `downloading`, Shoko events tried direct transition

### 3. State Machine Rejects Direct Transition
- `downloading -> anime_matching` is not a valid transition
- 15+ rejections logged at 16:24:01

### 4. Fallback Loop Can't Help
- Query: `WHERE requests.state IN ('GRABBING', 'DOWNLOADING') AND requests.qbit_hash IS NOT NULL`
- Request has `qbit_hash = None`, so never picked up

## Timeline

| Time | Event |
|------|-------|
| 16:09 | Request created (APPROVED) |
| 16:14 | Sonarr grabbed, state -> DOWNLOADING |
| 16:17 | Download progress visible (5.4%) |
| 16:18 | Progress dropped to 0% (qbit_hash issue) |
| 16:23 | Bluray download 100% complete |
| 16:24 | Sonarr imported all 12 episodes |
| 16:24 | Shoko SignalR sent 12 file:matched events |
| 16:24 | State machine rejected 15+ transitions |
| 16:50+ | Still stuck in `downloading` |

## Evidence

Shoko events received:
```
Legacy FileMatched raw data: {'FileID': 265, 'RelativePath': '/My Tiny Senpai/Season 1/[DiabloTripleA] My Tiny Senpai - S01E04.mkv', ...}
```
(All 12 episodes received)

State machine rejections:
```
app.core.state_machine - WARNING - Invalid transition for request 10: downloading -> anime_matching
```

## Suggested Fixes

### Option A: Fix Sonarr Grab Webhook
Ensure `qbit_hash` is always set when transitioning to DOWNLOADING state.

### Option B: Add Fallback for Missing qbit_hash
Modify fallback loop to also check requests in DOWNLOADING without qbit_hash after a timeout.

### Option C: Allow downloading -> anime_matching Transition
If files are matched by Shoko while still in DOWNLOADING state, allow the transition.

### Option D: Add Intermediate State Detection
When Import webhook is missed, detect imported files and force state progression.

## Workaround

Manual database update to force state to `anime_matching` or `available`.

## Related Issues

- UI Episode Status Inconsistency (2026-01-25-ui-episode-status-inconsistency.md)
- Manual search trigger caused duplicate torrents (cleaned up)
