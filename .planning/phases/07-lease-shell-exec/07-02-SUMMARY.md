---
phase: 07-lease-shell-exec
plan: 02
tasks_completed: 2
task_count: 2
date: 2026-04-19
duration_minutes: 10
executor: claude-haiku-4-5-20251001
status: complete
key_files_created:
  - just_akash/transport/lease_shell.py (modified)
  - tests/test_lease_shell_exec.py (modified)
key_files_modified:
  - just_akash/transport/lease_shell.py
  - tests/test_lease_shell_exec.py
commits:
  - 717f240: feat(07-02): implement token-expiry reconnect in LeaseShellTransport.exec()
  - a96998c: test(07-02): add token-refresh unit tests and helpers
decisions:
  - Implement token-expiry detection using close codes 4001/4003 and keyword matching on reason strings
  - Extract reconnect loop into _exec_with_refresh() method for cleaner separation of concerns
  - Use MAX_RECONNECT_ATTEMPTS=3 as a guard against infinite reconnection loops
  - Do NOT replay stdout/stderr on reconnect; accumulated output is delivered, new frames resume streaming
tests_passed: 450
tests_before: 443
tests_added: 7
coverage_percent: 74
deviations: none
---

# Phase 7 Plan 2: Token-Expiry Reconnect Summary

## Objective
Extend LeaseShellTransport.exec() to silently re-authenticate and reconnect when the provider closes the WebSocket due to JWT expiry, enabling long-running commands to survive the 30-second default JWT TTL.

## One-liner
JWT token expiry during exec now triggers automatic re-authentication with fresh JWT and reconnect loop; accumulated output persists, command continues streaming until completion or final exit code is received.

## Tasks Completed

### Task 1: Implement token-expiry reconnect in LeaseShellTransport.exec()

**Status:** Complete

**Changes:**
- Added `MAX_RECONNECT_ATTEMPTS = 3` module-level constant to guard against infinite loops
- Added `_is_auth_expiry_message(msg: str) -> bool` helper function to detect auth-related keywords: "expired", "unauthorized", "token" (case-insensitive)
- Added `_is_auth_expiry(exc: ConnectionClosedError) -> bool` helper function to detect auth-expiry conditions:
  - Close code 4001 (token expired)
  - Close code 4003 (unauthorized)
  - Close reason string matching auth keywords
  - Exception string fallback for RuntimeError cases
- Extracted the inner WebSocket receive loop from exec() into `_exec_with_refresh(command: str) -> int` private method:
  - Implements the outer retry loop (up to MAX_RECONNECT_ATTEMPTS)
  - On each attempt: fetches fresh JWT, reopens WebSocket connection
  - Inner loop: receives frames, dispatches output (codes 100/101), detects auth-expiry (code 4001/4003/reason)
  - On auth-expiry: breaks to outer loop for reconnect
  - On non-auth close: propagates error immediately (no retry)
  - On result frame (code 102): returns exit code
  - After MAX_RECONNECT_ATTEMPTS failures: raises RuntimeError with descriptive message
- Updated exec() to:
  - Calls prepare() if needed (sets _ws_url and _service)
  - Delegates to _exec_with_refresh(command)
  - Simplified from inline WebSocket loop to delegation pattern

**Design decisions:**
- No asyncio used (websockets.sync.client for synchronous execution)
- Output streamed to sys.stdout.buffer/sys.stderr.buffer is NOT replayed on reconnect
- Accumulated output persists across reconnects (user sees continuous stream)
- Only the new WebSocket frames (after reconnect) are processed
- RuntimeError handling also checks for auth keywords (frame code 103 failure messages)

**File modified:** just_akash/transport/lease_shell.py

### Task 2: Add token-refresh unit tests and run full suite

**Status:** Complete

**Changes:**
- Added imports: ConnectionClosedError, Close from websockets
- Added `make_close_error(code: int, reason: str = "") -> ConnectionClosedError` test helper to construct test exceptions
- Added 7 new test functions in TestTokenRefresh class:

1. `test_exec_reconnects_on_token_expiry`
   - Simulates first connect() raising ConnectionClosedError with code 4001
   - Second connect() succeeds with output + exit code
   - Asserts _fetch_jwt called twice (fresh JWT on retry)
   - Asserts exit code 0 returned correctly

2. `test_exec_reconnects_on_expired_message`
   - First connect() raises with reason="token expired"
   - Second connect() succeeds with exit code 2
   - Asserts _fetch_jwt called twice

3. `test_exec_raises_after_max_reconnect_attempts`
   - All connect() attempts raise code 4001
   - Asserts RuntimeError raised after MAX_RECONNECT_ATTEMPTS attempts
   - Asserts _fetch_jwt called exactly MAX_RECONNECT_ATTEMPTS times

4. `test_exec_non_auth_close_propagates`
   - Single connect() raises code 1006 (abnormal close, not auth)
   - Asserts ConnectionClosedError propagates immediately (NOT retried)
   - Asserts _fetch_jwt called only once

5. `test_is_auth_expiry_message`
   - Unit tests _is_auth_expiry_message() helper directly
   - True: "token expired", "unauthorized", "Token Expired" (case-insensitive), "contains token"
   - False: "connection reset", "timeout", empty string

6. `test_is_auth_expiry_with_close_code`
   - Code 4001 → True
   - Code 4003 → True
   - Code 1000 (normal) → False

7. `test_is_auth_expiry_with_reason_string`
   - Reason "token expired" → True
   - Reason "unauthorized" → True
   - Reason "connection reset" → False

**Test coverage:**
- All 41 tests in test_lease_shell_exec.py pass
- Full suite: 450 tests pass (7 new + 443 existing)
- No regressions detected
- Overall coverage: 74%
- lease_shell.py coverage: 91%

**Files modified:** tests/test_lease_shell_exec.py

## Verification Checklist

- [x] MAX_RECONNECT_ATTEMPTS = 3 constant exists at module level
- [x] _exec_with_refresh(command) method exists and implements retry loop
- [x] _is_auth_expiry(exc) and _is_auth_expiry_message(msg) module-level helpers exist
- [x] exec() calls prepare() if _ws_url is None, then delegates to _exec_with_refresh()
- [x] On ConnectionClosedError with close code 4001/4003 or reason containing "expired"/"unauthorized": reconnect with fresh JWT
- [x] On normal ConnectionClosedOK or result frame (code 102): return exit code immediately
- [x] After MAX_RECONNECT_ATTEMPTS failures: raise RuntimeError with descriptive message
- [x] All 7 token-refresh tests pass
- [x] All 450 tests pass with no regressions
- [x] No asyncio imports (synchronous websockets.sync.client only)
- [x] prepare() no longer raises NotImplementedError

## Success Criteria Met

- [x] _exec_with_refresh() implements retry loop with MAX_RECONNECT_ATTEMPTS = 3 guard
- [x] _is_auth_expiry() correctly identifies close codes 4001/4003 and "expired"/"unauthorized" strings
- [x] On auth expiry: new JWT fetched, new WebSocket opened, command continues streaming — user sees no error
- [x] On non-auth close: error propagates immediately (no retry)
- [x] After 3 failed reconnects: RuntimeError raised with descriptive message
- [x] All 5 required token-refresh tests plus 2 additional unit tests (7 total) pass
- [x] Complete test suite passes with no regressions (450 tests)

## Deviations from Plan

None - plan executed exactly as written.

## Auth Gates

None encountered.

## Technical Notes

**Reconnect detection strategy:**
- Primary: Close codes 4001 (token expired) and 4003 (unauthorized)
- Secondary: Close reason string matching (keywords: expired, unauthorized, token)
- Tertiary: RuntimeError message matching (for frame code 103 provider errors)

**Output handling:**
- stdout (code 100) and stderr (code 101) frames are written to sys.stdout.buffer and sys.stderr.buffer respectively
- On reconnect, accumulated output is NOT replayed
- New frames after reconnect append to existing output
- User sees continuous stream without duplication or silence

**Retry behavior:**
- Each retry fetches a fresh JWT via _fetch_jwt()
- Each retry opens a new WebSocket connection with fresh token
- Maximum 3 reconnection attempts (MAX_RECONNECT_ATTEMPTS)
- After 3 failures: RuntimeError with guidance to verify AKASH_API_KEY and deployment status

## Requirements Fulfilled

- [x] LSHL-03: Token-expiry reconnect implemented and tested

## Related Issues

Resolves: Issue #1 (Add WebSocket shell transport with token-expiry handling)
