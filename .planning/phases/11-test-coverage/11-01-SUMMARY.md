---
phase: 11-test-coverage
plan: "01"
subsystem: testing
tags: [pytest, websockets, unit-tests, token-refresh, reconnect, jwt]

requires:
  - phase: 07-lease-shell-exec
    provides: LeaseShellTransport, _exec_with_refresh, _is_auth_expiry, MAX_RECONNECT_ATTEMPTS

provides:
  - "8 unit tests covering all transport error paths: 4001/4003 auth expiry, reason-string expiry, max reconnect exhaustion, non-auth close propagation, frame 103 failure, fresh JWT verification"

affects:
  - 11-test-coverage

tech-stack:
  added: []
  patterns:
    - "FakeWebSocket copy pattern: copy helpers verbatim into each test file rather than importing from other test files to avoid cross-file coupling"
    - "patch transport._fetch_jwt (instance method) not global API for isolated token refresh tests"
    - "patch just_akash.transport.lease_shell.connect (module-level name) for WebSocket interception"

key-files:
  created:
    - tests/test_transport_errors.py
  modified: []

key-decisions:
  - "FakeWebSocket and make_close_error copied into test file (not imported from test_lease_shell_exec.py) to avoid cross-file coupling"
  - "All 8 tests use bare functions (no class grouping) as specified by plan"
  - "Test 8 inspects call_args_list[n].kwargs['additional_headers']['Authorization'] to verify JWT is not cached between reconnect calls"

patterns-established:
  - "Transport error tests: construct transport, call prepare(), patch _fetch_jwt with side_effect list, patch module-level connect, verify call counts and header values"

requirements-completed:
  - TEST-02

duration: 10min
completed: 2026-04-19
---

# Phase 11 Plan 01: Transport Error Tests Summary

**8 unit tests covering token-expiry reconnect (4001/4003/reason-string), MAX_RECONNECT_ATTEMPTS exhaustion, non-auth close propagation, frame 103 failure, and fresh-JWT header verification via call_args_list**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-19T00:00:00Z
- **Completed:** 2026-04-19T00:10:00Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Created `tests/test_transport_errors.py` with 8 genuine assertions covering all named error paths
- Full suite grew from 483 to 491 tests, all passing, zero regressions
- TEST-02 requirement satisfied: token refresh (4001/4003/reason-string), error frame 103, and max-reconnect exhaustion all have named test coverage in a dedicated file

## Task Commits

1. **Task 1: Write test_transport_errors.py** - `122b4c3` (test)

## Files Created/Modified

- `tests/test_transport_errors.py` - 8 unit tests for transport error paths and token refresh

## Decisions Made

- FakeWebSocket and make_close_error copied verbatim into the new file rather than imported from `test_lease_shell_exec.py` — avoids cross-file coupling as specified by the plan
- Used bare function form (not class-based grouping) for all 8 tests — matches plan specification
- Test 8 uses `mock_connect.call_args_list[n].kwargs["additional_headers"]["Authorization"]` to directly verify the JWT changes between the first and second connect call, confirming the token is not cached between reconnect attempts

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all 8 tests passed on first run. Implementation in `_exec_with_refresh()` was already correct; tests confirm existing behaviour with explicit assertions.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- TEST-02 requirement is satisfied
- Token-refresh reconnect loop has explicit named coverage
- Full test suite at 491 tests, all green
- Ready to proceed with remaining 11-test-coverage plans

---
*Phase: 11-test-coverage*
*Completed: 2026-04-19*
