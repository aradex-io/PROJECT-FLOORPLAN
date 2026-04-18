# Phase 3 & 4 — Passive Surveillance, Tracking & Persistence

**Date**: 25 Mar 2026
**Author**: Claude
**Status**: final

## Objective

Complete Phase 3 (Passive Surveillance) and Phase 4 (Tracking & Persistence) by
fixing identified bugs, adding comprehensive test coverage, and validating all
implementations work correctly.

## Context

Code review found that **all Phase 3 and 4 implementations are code-complete** but
have critical bugs and near-zero test coverage:

| Module | Lines | Implementation | Tests |
|--------|-------|---------------|-------|
| `passive/monitor.py` | 166 | Complete | 0 |
| `passive/probe_tracker.py` | 208 | Complete | 0 |
| `passive/ftm_capture.py` | 304 | Complete | 0 |
| `tracking/device.py` | 109 | Complete | 0 (indirect via manager) |
| `tracking/fingerprint.py` | 156 | Complete | 5 |
| `tracking/manager.py` | 239 | Complete | 8 |
| `db/store.py` | 376 | Complete | 0 |

### Bugs Found

1. **`ftm_capture.py:248`** — `_exchanges[key]` accessed outside lock (race condition)
2. **`fingerprint.py:151`** — divide-by-zero when `avg_ftm_response_time_us == 0`
3. **`store.py:128`** — `_cursor()` doesn't check `_conn is not None`
4. **`probe_tracker.py:136`** — no depth limit on Dot11Elt iteration

## Approach

### Phase 3: Bug Fixes + Tests

#### 3a. Fix bugs in passive modules

1. **ftm_capture.py**: Move `_exchanges[key]` access inside the existing lock block
2. **probe_tracker.py**: Add max iteration depth (100) to Dot11Elt parsing loop

#### 3b. Tests for passive modules (`tests/test_passive/`)

Since passive modules depend on scapy and root-level monitor mode, tests must use
**mocks** — no real Wi-Fi hardware.

**`test_probe_tracker.py`** (~8 tests):
- Mock scapy packet with Dot11ProbeReq + RadioTap layers
- Test MAC extraction and randomization detection
- Test SSID parsing (present, empty, missing)
- Test RSSI extraction and history capping
- Test callback invocation on sighting
- Test device aggregation (multiple probes → one device)
- Test start/stop lifecycle

**`test_ftm_capture.py`** (~8 tests):
- Mock 802.11 Action frame with correct category/action codes
- Test FTM request parsing (initiator/responder identification)
- Test FTM response parsing
- Test exchange recording and burst counting
- Test callback invocation
- Test device role tracking (initiator vs responder)
- Test start/stop lifecycle

**`test_monitor.py`** (~5 tests):
- Mock subprocess calls for `iw` commands
- Test enable/disable lifecycle
- Test channel switching
- Test channel-to-frequency conversion
- Test context manager cleanup

### Phase 4: Bug Fixes + Tests

#### 4a. Fix bugs in tracking/db modules

1. **fingerprint.py**: Guard divide-by-zero in timing comparison
2. **store.py**: Add `_conn is not None` check in `_cursor()`

#### 4b. Tests for TrackedDevice (`tests/test_tracking/test_device.py`) (~8 tests):
- Test position update and history tracking
- Test confidence scoring at various uncertainty levels
- Test mark_stale transitions (ACTIVE → STALE → LOST)
- Test MAC history tracking
- Test zone dwell time calculation
- Test to_dict serialization
- Test history cap (max 1000)

#### 4c. Tests for SessionStore (`tests/test_db/test_store.py`) (~10 tests):
- Test connect and schema creation
- Test session lifecycle (start → record → end)
- Test record_position and retrieval via get_position_track
- Test record_ranging
- Test record_device with MAC history serialization
- Test record_zone_event and filtered queries
- Test get_session_stats
- Test context manager
- Test multiple sessions
- Test empty queries (no records)

#### 4d. Expand TrackManager tests (~5 new tests):
- Test stale/lost timeout transitions via cleanup_stale()
- Test dwell time alerting (max_dwell_time exceeded)
- Test device callbacks (not just zone callbacks)
- Test MAC randomization detection with fingerprinting
- Test concurrent device updates

## Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Scapy mock complexity | Use simple mock objects matching Dot11/RadioTap API; don't over-mock |
| SQLite test isolation | Use `:memory:` database or tmpdir; no disk state leakage |
| Subprocess mocking for monitor.py | Use `unittest.mock.patch` on `subprocess.run` |
| Thread safety tests are flaky | Avoid timing-dependent assertions; test state, not scheduling |

## Success Criteria

1. All 4 bugs fixed
2. ≥40 new tests added (8 probe + 8 ftm + 5 monitor + 8 device + 10 db + 5 manager)
3. `python -m pytest tests/ -v` all pass (expected: ~120+ total)
4. `ruff check` and `mypy` clean
5. All Phase 3 and Phase 4 roadmap items marked complete
6. No test requires root, Wi-Fi hardware, or scapy packet capture
