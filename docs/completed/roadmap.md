# FLOORPLAN — Completed Roadmap Items

Checked items have been implemented, tested, and merged.

## Phase 0 — Foundation

- [x] Project scaffolding (pyproject.toml, src layout, frontend skeleton)
- [x] CLAUDE.md development rules
- [x] Documentation artifact structure (`docs/`)
- [ ] CI pipeline (lint, type-check, test)
- [ ] Dev environment setup guide

## Phase 1 — Ranging Engine

- [ ] nl80211 FTM request/response via pyroute2
- [ ] Simulation mode for hardware-free development
- [ ] Calibration routines (bias correction, per-AP offsets)
- [ ] NLOS detection and mitigation

## Phase 2 — Position Engine

- [ ] Trilateration (least-squares, weighted)
- [ ] Kalman filter (constant-velocity model)
- [ ] Particle filter (for non-Gaussian environments)
- [ ] Engine orchestration (filter selection, fallback)

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
