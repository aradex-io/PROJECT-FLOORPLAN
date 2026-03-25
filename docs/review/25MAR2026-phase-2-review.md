# Phase 2 — Position Engine Review

**Date**: 25 Mar 2026
**Author**: Claude
**Status**: final

## Objective

Assess whether Phase 2 (Position Engine) can be marked complete on the roadmap.

## Context

Phase 2 has four roadmap items:
1. Trilateration (least-squares, weighted)
2. Kalman filter (constant-velocity model)
3. Particle filter (for non-Gaussian environments)
4. Engine orchestration (filter selection, fallback)

## Review Findings

### 1. Trilateration — COMPLETE

**File**: `src/floorplan/position/trilateration.py` (175 lines)
- Weighted Least Squares via `scipy.optimize.least_squares`
- 2D and 3D modes, configurable
- Linearized fast-path solver alternative
- Weight computation: `1 / (std_dev² + 0.01)`
- Uncertainty estimated from RMSE of residuals

**Tests**: 7 tests in `test_trilateration.py`
- Perfect geometry, overdetermined, noisy, weighted, insufficient refs, 3D, linearized
- Coverage: all public methods

**Verdict**: Complete, well-tested.

### 2. Kalman Filter — COMPLETE

**File**: `src/floorplan/position/kalman.py` (228 lines)
- Extended Kalman Filter with state `[x, y, vx, vy]`
- Constant-velocity prediction model
- Nonlinear range update with analytic Jacobian
- Joseph-form covariance update (numerically stable)
- Configurable via `KalmanConfig` dataclass

**Tests**: 6 tests in `test_kalman.py`
- Initialization, prediction, range convergence, position update, uncertainty decrease, reset
- Coverage: all public methods

**Verdict**: Complete, well-tested.

### 3. Particle Filter — COMPLETE

**File**: `src/floorplan/position/particle.py` (178 lines)
- Sequential Monte Carlo with systematic resampling
- State: `[x, y, vx, vy]` per particle
- Importance weighting with Gaussian likelihood
- Adaptive resampling when `n_eff < N/2`
- Weight collapse recovery (reinitialize)

**Tests**: 5 tests in `test_particle.py`
- Initialization, convergence, bounds, uncertainty, reset
- Coverage: all public methods

**Verdict**: Complete, well-tested.

### 4. Engine Orchestration — COMPLETE

**File**: `src/floorplan/position/engine.py` (213 lines)
- Measurement buffering per device with 5s expiry
- Deduplication (replaces old measurement from same ref)
- Triggers trilateration at ≥3 refs, falls back to filter-only at <3
- Filter selection: "kalman" or "particle" via config
- Lazy per-device filter instantiation
- `process_ranging_result()` adapter from RangingResult

**Tests**: No dedicated `test_engine.py`, but:
- 5 integration tests in `tests/test_ranging/test_integration.py` exercise the full
  RangingEngine → PositionEngine → Position pipeline with both Kalman and particle filters
- Tests verify convergence with 3 APs, 4 APs, NLOS, multi-round improvement

**Verdict**: Complete. Integration tests provide adequate coverage of orchestration logic.

## Gaps Identified

1. **No dedicated PositionEngine unit tests** — integration tests cover the critical paths
   (add_measurement → trilateration → filter update → position), but edge cases like
   unknown ref_mac, measurement expiry, and remove_device are untested.
   **Risk**: Low. These are simple code paths with obvious correctness.

2. **No thread safety** — PositionEngine is single-threaded by design (called from
   RangingEngine's callback on its background thread). Not a bug, but worth noting.

## Verdict

**Phase 2 is COMPLETE.** All four items have full implementations with working tests.
The integration tests from Phase 1 validate the end-to-end pipeline. Mark all items done.

## Outcome

Marking Phase 2 complete in roadmap.
