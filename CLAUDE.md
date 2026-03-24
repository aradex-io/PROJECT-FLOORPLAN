# FLOORPLAN — Development Rules

## Project Overview

FLOORPLAN is a Wi-Fi FTM (Fine Time Measurement) / RTT (Round-Trip Time) indoor
positioning and passive surveillance system. It uses 802.11mc ranging to trilaterate
device positions on a floor plan, with Kalman/particle filtering for smoothing,
NLOS detection, and a real-time web dashboard.

## Architecture

```
cli/          — Click CLI entrypoint (floorplan command)
config/       — YAML site config loader + Pydantic models
ranging/      — nl80211 FTM/RTT engine, calibration, NLOS detection
position/     — Trilateration, Kalman filter, particle filter
passive/      — Monitor-mode FTM capture, probe request tracking
tracking/     — Device manager, fingerprint correlation
db/           — SQLite session storage (aiosqlite)
web/          — FastAPI app, REST routes, WebSocket push
frontend/     — React + TypeScript + Tailwind dashboard
```

Data flow: `ranging → position → tracking → web/ws → frontend`

## Process for Every Action

For every action, the process will go as follows:

1. **Plan** — Outline the approach, identify files to change, and define success criteria. Write the plan to `docs/planning/<DDMMMYYYY>.md` (e.g. `docs/planning/23MAR2026.md`)
2. **Critical Review of the Plan** — Challenge assumptions, identify risks, consider edge cases, and evaluate alternatives before proceeding. Append review notes to the same planning doc or write to `docs/review/<DDMMMYYYY>-<topic>.md`
3. **Finalize the Plan** — Incorporate review feedback and lock down the approach
4. **Execute the Plan** — Implement changes according to the finalized plan
5. **Verify the Plan Benchmarks** — Confirm that success criteria are met, run relevant tests, and validate behavior
6. **Create Test Cases** — If applicable, write test cases for the implemented pieces to ensure correctness and prevent regressions
7. **Record Completion** — Update `docs/completed/roadmap.md` checklist when a milestone or roadmap item is done

## Documentation Artifacts

All research, planning, and review documents live under `docs/`:

```
docs/
├── planning/       — Plans, proposals, phase outlines
│   └── <DDMMMYYYY>.md or <DDMMMYYYY>-<topic>.md
├── review/         — Critical reviews, audits, retrospectives
│   └── <DDMMMYYYY>-<topic>.md
├── reference/      — Technical references, protocol notes, research
│   └── <descriptive-name>.md
└── completed/      — Roadmap completion tracking
    └── roadmap.md  — Checklist of completed milestones
```

### Naming Conventions

- **Date format**: `DDMMMYYYY` — e.g. `24MAR2026` (day, abbreviated month uppercase, four-digit year)
- **Topic slug**: lowercase, hyphen-separated — e.g. `phase-0-review`, `nlos-algorithm`, `kalman-tuning`
- **Full examples**:
  - `docs/planning/24MAR2026-phase-1-ranging.md`
  - `docs/review/24MAR2026-ftm-accuracy-audit.md`
  - `docs/reference/80211mc-ftm-protocol.md`
  - `docs/completed/roadmap.md`

### Document Template

All planning and review documents should follow this structure:

```markdown
# <Title>

**Date**: <DD MMM YYYY>
**Author**: <name>
**Status**: draft | in-review | final

## Objective

What we are trying to accomplish.

## Context

Background, prior work, constraints.

## Approach

Detailed plan or analysis.

## Risks & Mitigations

Known risks and how to handle them.

## Success Criteria

Measurable outcomes that define "done".

## Outcome

(Filled after execution) What actually happened, lessons learned.
```

## Project Structure

- Python package: `src/floorplan/`
- Tests: `tests/`
- Frontend: `frontend/`
- Config examples: `examples/`
- Documentation: `docs/`

## Tech Stack

- Python 3.10+ (numpy, scipy, scapy, pyroute2, FastAPI, Click)
- React + TypeScript + Tailwind CSS (frontend)
- SQLite (session storage via aiosqlite)
- YAML (site configuration)
- Pydantic v2 (data models and validation)

## Development Guidelines

### Commands

- Run tests: `python -m pytest tests/ -v`
- Lint: `ruff check src/ tests/`
- Type check: `mypy src/`
- Run dev server: `floorplan serve --config examples/site.yml`

### Code Conventions

- Line length: 100 characters (enforced by ruff)
- Use `async`/`await` for all I/O (database, network, WebSocket)
- Pydantic models for all config and API schemas — no raw dicts at boundaries
- Type annotations on all public functions
- Tests use simulation mode — never require Wi-Fi hardware or root

### Security

- All nl80211 operations require root/CAP_NET_ADMIN — never assume privilege in library code
- MAC addresses are PII — sanitize in logs unless debug mode is explicit
- WebSocket endpoints must validate origin
- No secrets in config examples or committed YAML

### Commit Messages

Use conventional format:

```
<type>(<scope>): <short summary>

<optional body>
```

Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`
Scopes: `ranging`, `position`, `passive`, `tracking`, `web`, `cli`, `config`, `db`, `frontend`
