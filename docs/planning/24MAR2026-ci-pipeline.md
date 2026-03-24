# CI Pipeline Setup

**Date**: 24 MAR 2026
**Author**: Jay (d0sf3t)
**Status**: draft

## Objective

Set up a GitHub Actions CI pipeline that runs lint, type-check, and tests on every
push and pull request, catching regressions before code merges.

## Context

- No `.github/` directory exists yet — greenfield CI setup
- `pyproject.toml` already defines dev dependencies: `pytest`, `pytest-asyncio`,
  `pytest-cov`, `ruff`, `mypy`
- 13 test files exist across `test_position/`, `test_ranging/`, `test_tracking/`
- Project targets Python 3.10+ (`requires-python = ">=3.10"`)
- All tests use simulation mode — no hardware or root required in CI
- mypy is configured with `strict = true`
- ruff selects rules: E, F, W, I, N, UP, B, SIM at line-length 100

## Approach

### Single workflow file: `.github/workflows/ci.yml`

**Trigger**: push to `main` and all PRs

**Matrix**: Python 3.10, 3.11, 3.12 — ensures forward compatibility

**Jobs** (3 parallel jobs for fast feedback):

1. **lint** — `ruff check src/ tests/` + `ruff format --check src/ tests/`
2. **type-check** — `mypy src/`
3. **test** — `pytest tests/ -v --tb=short` (matrix across Python versions)

### Dependency installation

- Use `pip install -e ".[dev]"` to install the package with dev dependencies
- Cache pip downloads via `actions/setup-python` built-in caching

### Design decisions

- **3 separate jobs** rather than 1 sequential job — lint and type-check don't need
  to wait for tests, and failures are easier to diagnose
- **No coverage upload** yet — keep it simple for Phase 0; can add codecov in Phase 6
- **No frontend CI** yet — frontend build/lint is a separate concern for Phase 5
- **ruff format check** added alongside lint — enforces consistent formatting from day one

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| mypy strict mode may fail on existing code | Run mypy locally first; fix any errors before merging |
| scapy/pyroute2 may have install issues in CI | These are pure pip installs; no system deps needed |
| Tests may be flaky with async | pytest-asyncio `auto` mode is already configured |
| ruff format check may fail on existing code | Run ruff format locally first; fix before merging |

## Success Criteria

1. All three jobs (lint, type-check, test) pass in CI
2. Pipeline runs on push to `main` and on PRs
3. Python 3.10, 3.11, 3.12 all pass
4. Total CI time under 3 minutes
5. Existing codebase passes all checks without modifications (or fixes are included)
