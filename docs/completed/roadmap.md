# FLOORPLAN — Completed Roadmap Items

Checked items have been implemented, tested, and merged.

## Phase 0 — Foundation

- [x] Project scaffolding (pyproject.toml, src layout, frontend skeleton)
- [x] CLAUDE.md development rules
- [x] Documentation artifact structure (`docs/`)
- [x] CI pipeline (lint, type-check, test)
- [ ] Dev environment setup guide

## Phase 1 — Ranging Engine

- [x] nl80211 FTM request/response via pyroute2
- [x] Simulation mode for hardware-free development
- [x] Calibration routines (bias correction, per-AP offsets)
- [x] NLOS detection and mitigation

## Phase 2 — Position Engine

- [x] Trilateration (least-squares, weighted)
- [x] Kalman filter (constant-velocity model)
- [x] Particle filter (for non-Gaussian environments)
- [x] Engine orchestration (filter selection, fallback)

## Phase 3 — Passive Surveillance

- [ ] Monitor-mode FTM frame capture
- [ ] Probe request tracking and MAC correlation
- [ ] Device fingerprinting

## Phase 4 — Tracking & Persistence

- [ ] Device lifecycle manager
- [ ] SQLite session storage
- [ ] Historical trajectory queries

## Phase 5 — Web Dashboard

- [ ] FastAPI REST API
- [ ] WebSocket real-time push
- [ ] React floor plan viewer
- [ ] Device info panel

## Phase 6 — Hardening

- [ ] Security audit (WebSocket origin, MAC sanitization)
- [ ] Performance profiling
- [ ] Deployment documentation
