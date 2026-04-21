# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-04-19)

**Core value:** Fastest path from "I want something running on Akash" to a live, remotely-accessible instance — single command, no manual portal steps.
**Current focus:** v1.5 milestone complete — ready for /nf:complete-milestone

## Current Position

Phase: 11 of 11 (Test Coverage) — COMPLETE
Plan: 2 of 2 in phase 11 — COMPLETE
Status: Phase 11 verified — all must-haves satisfied (16/16)
Last activity: 2026-04-19 — Phase 11 verification passed: 491 tests, TEST-01 and TEST-02 satisfied

Progress: [████████████████████] 11/11 phases complete (100%)

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
| Phase 11 P02 | 12 | 2 tasks | 2 files |

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
- **[Phase 10-02] Lease-shell is now default transport** — users get lease-shell by default; SSH via --transport ssh
- **[Phase 10-02] Automatic fallback via validate() check** — when lease-shell unavailable, falls back to SSH with notice to stderr
- **[Phase 11] test_transport_errors.py is a standalone file** — FakeWebSocket copied (not imported) to avoid cross-file coupling
- **[Phase 11] connect() E2E is manual-only** — subprocess-based E2E cannot automate full-duplex TTY; inject-verify-via-exec is the automated substitute
- [Phase 11]: [Phase 11-02] No connect() step in E2E orchestrator — connect() requires interactive TTY; inject+verify-via-exec is the automated substitute
- [Phase 11]: [Phase 11-02] just test-shell recipe follows test/test-secrets pattern — consistent Justfile recipe structure for all E2E tests

### Pending Todos

None.

### Blockers/Concerns

- Self-signed cert acceptance (Phase 7 shortcut) — cert pinning deferred, review before shipping v1.5
- Transport fallback duplicated 3× in cli.py (cleanup report recommends extracting helper) — low urgency

## Session Continuity

Last session: 2026-04-19
Stopped at: Milestone v1.5 audit: passed (17/17 requirements). Report: .planning/milestones/v1.5-MILESTONE-AUDIT.md. Ready for /nf:complete-milestone.
Resume file: None
