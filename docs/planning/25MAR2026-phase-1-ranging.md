# Phase 1 — Ranging Engine Completion

**Date**: 25 Mar 2026
**Author**: Claude
**Status**: final

## Objective

Complete all four Phase 1 roadmap items for the ranging engine, enabling full
hardware-free development and testing of the ranging → position → tracking pipeline.

## Context

Current state of Phase 1 items:

| Item | Status | Notes |
|------|--------|-------|
| nl80211 FTM request/response | Code exists (`nl80211.py`) | 397 lines, full netlink impl + basic sim fallback |
| Simulation mode | Minimal (`_simulate_ftm`) | Random noise only, not configurable |
| Calibration routines | **Done** | `calibration.py` + 7 passing tests |
| NLOS detection | **Done** | `nlos.py` + 5 passing tests |

Key gaps:
1. **No tests** for `RangingEngine` (267 lines, untested)
2. **No tests** for `NL80211Interface` (397 lines, untested)
3. **Simulation mode is too basic** — hardcoded 5m base distance, no scenario control
4. **No configurable simulator** — can't model specific AP layouts, NLOS, multipath
5. **No integration test** for the ranging → position pipeline

## Approach

### 1. FTM Simulator (`src/floorplan/ranging/simulator.py`)

Create a configurable FTM simulator that replaces `_simulate_ftm`:

- **SimulatedAP**: Dataclass with position (x, y, z), MAC, channel, LOS/NLOS flag
- **SimulationScenario**: Collection of APs + device position + noise parameters
- **FTMSimulator**: Generates realistic FTMResult objects given a device position
  - Computes true distances from geometry
  - Adds Gaussian noise (configurable std_dev per AP)
  - Models NLOS with positive bias + increased variance
  - Supports multipath (occasional outlier bursts)
  - Generates realistic RTT values (distance → picoseconds)
  - RSSI modeled via free-space path loss

### 2. Wire Simulator into NL80211Interface

- Add `simulation_mode` flag and `simulator` attribute to NL80211Interface
- When simulation_mode=True, `start_ftm_measurement` delegates to simulator
- Simulator is injectable (for tests) or auto-created from site config

### 3. Tests for NL80211Interface (`tests/test_ranging/test_nl80211.py`)

- Test simulation mode produces valid FTMResult objects
- Test burst parameter handling (num_bursts, ftms_per_burst)
- Test FTM capability check in simulation mode
- Test connect/close lifecycle in simulation mode

### 4. Tests for RangingEngine (`tests/test_ranging/test_engine.py`)

- Test single-target ranging (range_once)
- Test multi-target continuous ranging
- Test result callbacks
- Test NLOS flagging through the engine
- Test calibration correction through the engine
- Test history retrieval
- Test target add/remove

### 5. Integration Test (`tests/test_ranging/test_integration.py`)

- End-to-end: simulator → RangingEngine → PositionEngine → Position
- Verify that a simulated device converges to correct position
- Test with 3 and 4 reference points
- Test with one NLOS AP (verify degraded but valid position)

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Simulator may not be realistic enough | Model based on published 802.11mc error profiles; good enough for dev |
| Thread safety in RangingEngine tests | Use short intervals, explicit stop, join threads |
| Flaky timing-dependent tests | Use deterministic seeds for random noise; avoid tight timing assertions |
| Over-engineering the simulator | Keep it minimal — just enough for tests, not a full RF simulator |

## Success Criteria

1. `python -m pytest tests/test_ranging/ -v` passes with ≥20 new tests
2. `RangingEngine` has full unit test coverage (all public methods)
3. `NL80211Interface` simulation mode tested
4. Integration test proves ranging → position convergence within 2m error
5. All existing 44 tests still pass
6. `ruff check` and `mypy` still clean
7. Simulation mode is configurable via `FTMSimulator` (injectable)
