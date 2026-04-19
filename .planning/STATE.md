# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-19)

**Core value:** Fastest path from "I want something running on Akash" to a live, remotely-accessible instance — single command, no manual portal steps.
**Current focus:** Phase 10 — Default Transport Switch and Fallback (v1.5)

## Current Position

Phase: 9 of 11 (Interactive Shell) — COMPLETE
Plan: 3 of 3 in phase 9 (COMPLETE)
Status: Phase 9 complete — LeaseShellTransport.connect() implemented; 475 tests passing
Last activity: 2026-04-19 — Phase 9 Plans 1-3 (TTY interactive shell) executed successfully

Progress: [████████████████████] 8/8 plans (100%)

## Performance Metrics

**Velocity:**
- Total plans completed: 2
- Average duration: 3.0 minutes
- Total execution time: 0.1 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 6 | 1 | 2.0 min | 2.0 min |
| 7 | 1 | 4.0 min | 4.0 min |

**Recent Trend:**
- Last 5 plans: —
- Trend: —
| Phase 07-lease-shell-exec P02 | 10 | 2 tasks | 2 files |

## Accumulated Context

### Decisions

- Project is brownfield CLI at v1.4.0 (357 tests, 69% coverage)
- v1.5 switches default transport from SSH to lease-shell WebSocket
- Phase 6 must include protocol reverse-engineering before any WebSocket code is written
- Token refresh (LSHL-03) must be implemented in Phase 7 alongside exec — not deferred
- New dependencies: websockets>=16.0, pexpect>=4.9.0
- Active branch: feature/issue-1-add-websocket-shell-transport
- **[06-01] Transport abstraction uses ABC pattern with factory function** — decouples CLI from transport selection
- **[06-01] SSHTransport delegates to api.py helpers** — zero behavior change, ensures parity with v1.4
- **[06-01] LeaseShellTransport is stub** — full implementation deferred to Phase 7 after protocol discovery
- **[07-01] Synchronous websockets client (websockets.sync.client)** — exec() is synchronous; no asyncio
- **[07-01] Self-signed cert acceptance in Phase 7** — custom SSL context; validation deferred to Phase 8
- **[07-01] JWT TTL fallback logic** — request 3600s but accept server cap (30s); Phase 8 handles refresh
- [Phase 07-lease-shell-exec]: Token-expiry detection via close codes 4001/4003 + keyword matching on reason strings
- [Phase 07-lease-shell-exec]: Output NOT replayed on reconnect; accumulated stdout/stderr persists, new frames resume streaming

### Pending Todos

None yet.

### Blockers/Concerns

- Self-signed cert acceptance (Phase 7 shortcut) — cert pinning deferred to Phase 10+; review before shipping v1.5
- Phase 10 (default transport switch + fallback) is next — switches default from SSH to lease-shell; adds fallback logic

## Session Continuity

Last session: 2026-04-19
Stopped at: Phase 9 complete — 3 plans executed, 475 tests passing, VERIFICATION.md: passed. Ready for Phase 10 (Default Transport Switch and Fallback).
Resume file: None
