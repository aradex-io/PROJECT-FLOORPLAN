# Phase 1 — Critical Review

**Date**: 25 Mar 2026
**Author**: Claude
**Status**: final

## Objective

Challenge assumptions and identify risks in the Phase 1 plan before execution.

## Context

Reviewed `ranging/engine.py` (267 lines), `ranging/nl80211.py` (397 lines),
`position/engine.py` (213 lines), and all existing tests.

## Review Findings

### 1. Existing `_simulate_ftm` is insufficient but not wrong

The current simulation (nl80211.py:357-389) generates random 1-10m distances with
200mm Gaussian noise. It's functional but:
- Not deterministic (no seed control → flaky tests)
- No geometry awareness (ignores actual AP positions)
- No NLOS modeling
- RSSI is random (not correlated to distance)

**Decision**: Replace with injectable `FTMSimulator` class that computes distances
from geometry. Keep the old `_simulate_ftm` as a fallback when no simulator is
injected (backward compatible).

### 2. RangingEngine has tight coupling to NL80211Interface

`engine.py:58` creates `NL80211Interface(interface)` directly. For testability,
we need to inject the nl80211 instance or a simulator.

**Decision**: Add optional `nl80211` parameter to `RangingEngine.__init__`. If not
provided, create one. This is minimal surgery — one parameter added.

### 3. Thread safety in tests

`start_continuous` spawns a daemon thread. Tests must:
- Use deterministic simulator (no real sleep)
- Call `stop_continuous` and join reliably
- Avoid race conditions in assertions

**Decision**: Keep scan interval >0 in tests to avoid tight loops. Use
`threading.Event` or short sleeps for sync. Use `range_once` for most unit tests
(avoids threads entirely).

### 4. Integration test scope

The plan calls for ranging → position integration. This is valuable but:
- Don't need to test TrackManager (already tested)
- Focus on: simulator → RangingEngine → PositionEngine → Position converges

**Decision**: Single integration test file with 3-4 tests. No web/db integration.

### 5. Calibration and NLOS are already done

Both have implementations + passing tests. The plan correctly identifies these as
complete. No changes needed to `calibration.py` or `nlos.py`.

**Decision**: Mark these items as done in the roadmap after verifying they integrate
correctly through the engine (integration test covers this implicitly).

### 6. Risk: Over-engineering the simulator

RF simulation is a rabbit hole. We need just enough to:
- Generate deterministic results for known geometries
- Model LOS vs NLOS (bias + variance)
- Produce valid FTMResult objects

**Decision**: ~100-150 lines max. No multipath modeling, no wall attenuation,
no frequency-dependent effects. Save those for Phase 6 hardening.

## Success Criteria

Same as plan — ≥20 new tests, full coverage of public methods, integration
convergence within 2m, all checks clean.

## Outcome

Review complete. Plan is sound with the adjustments noted above. Proceeding to
execution.
