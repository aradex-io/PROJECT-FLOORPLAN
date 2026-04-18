# Phase 3 & 4 — Critical Review of Plan

**Date**: 25 Mar 2026
**Author**: Claude
**Status**: final

## Objective

Challenge the Phase 3 & 4 plan before execution.

## Review Findings

### 1. Scope is appropriate

The plan focuses on **bug fixes + tests only** since all code is already written.
This is the right call — no new features, just validation. Estimated ~44 new tests
is achievable in a single session.

### 2. Mock strategy for scapy is correct

Passive modules (probe_tracker, ftm_capture) use `scapy.sniff()` which requires
root and a monitor-mode interface. Mocking at the packet level (creating mock objects
with `.haslayer()`, `.getlayer()`, `addr1`, `addr2` attributes) is the standard
approach. Don't mock sniff itself — test `_process_probe()` and `_process_frame()`
directly with crafted packets.

**Decision**: Call the processing methods directly with mock packet objects. Skip
testing the sniff loop (it's trivial glue code).

### 3. SQLite tests should use in-memory database

`:memory:` databases are fast and automatically cleaned up. The `SessionStore`
constructor accepts a `db_path` parameter — pass `":memory:"` in tests.

**Decision**: Confirmed — no disk I/O in tests.

### 4. MonitorMode tests are low-value

`monitor.py` wraps `subprocess.run("iw ...")` calls that require root. Mocking
subprocess is possible but the tests would just verify mock behavior, not real
interface management. The channel-to-frequency conversion is the only pure logic.

**Decision**: Test only `_channel_to_freq()` and the context manager lifecycle with
mocked subprocess. Skip testing actual iw commands — that's integration testing for
real hardware.

### 5. Bug #4 (Dot11Elt infinite loop) is theoretical

Scapy's Dot11Elt uses a standard linked-list `payload` attribute. Circular references
would require a malformed packet crafted specifically to exploit this. In practice,
scapy handles packet parsing safely.

**Decision**: Skip this fix. It's defensive coding against an implausible scenario
that would add complexity without value. If needed later, add during Phase 6 hardening.

### 6. Revised bug list (3 bugs, not 4)

1. **ftm_capture.py:248** — race condition in exchange access → FIX
2. **fingerprint.py:151** — divide-by-zero → FIX
3. **store.py:128** — missing connection check → FIX

### 7. Test count estimate

| Module | Tests | Rationale |
|--------|-------|-----------|
| probe_tracker | 7 | Process method + MAC detection + aggregation |
| ftm_capture | 7 | Frame parsing + exchange recording + device roles |
| monitor | 3 | Channel conversion + context manager |
| device | 7 | Position, stale, confidence, dwell, serialization |
| store | 10 | Full CRUD lifecycle |
| manager (new) | 5 | Stale cleanup, dwell alert, device callback |

**Total: ~39 new tests** (conservative). Plan says ≥40 — close enough.

## Verdict

Plan is sound. Minor adjustments:
- Drop bug #4 (Dot11Elt depth limit)
- Reduce monitor.py tests to 3 (channel conversion focus)
- Test passive modules by calling processing methods directly (not mocking sniff)

Proceed with execution.
