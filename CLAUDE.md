# FLOORPLAN — Development Rules

## Process for Every Action

For every action, the process will go as follows:

1. **Plan** — Outline the approach, identify files to change, and define success criteria
2. **Critical Review of the Plan** — Challenge assumptions, identify risks, consider edge cases, and evaluate alternatives before proceeding
3. **Finalize the Plan** — Incorporate review feedback and lock down the approach
4. **Execute the Plan** — Implement changes according to the finalized plan
5. **Verify the Plan Benchmarks** — Confirm that success criteria are met, run relevant tests, and validate behavior
6. **Create Test Cases** — If applicable, write test cases for the implemented pieces to ensure correctness and prevent regressions

## Project Structure

- Python package: `src/floorplan/`
- Tests: `tests/`
- Frontend: `frontend/`
- Config examples: `examples/`

## Tech Stack

- Python 3.10+ (numpy, scipy, scapy, pyroute2, FastAPI, Click)
- React + TypeScript + Tailwind CSS (frontend)
- SQLite (session storage)
- YAML (site configuration)

## Development Guidelines

- Run tests with: `python -m pytest tests/ -v`
- Lint with: `ruff check src/ tests/`
- Type check with: `mypy src/`
- The ranging engine has a simulation mode for development without Wi-Fi hardware
- All nl80211 operations require root/CAP_NET_ADMIN — tests use simulation mode
