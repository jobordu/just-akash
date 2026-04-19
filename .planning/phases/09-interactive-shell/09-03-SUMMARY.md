---
plan: 09-03
status: complete
tasks_completed: 2
tasks_total: 2
key_files:
  modified:
    - tests/test_transport.py
    - tests/test_transport_cli_integration.py
    - tests/test_lease_shell_exec.py
---

# Plan 09-03: Update Existing Tests for Phase 9

## What Was Built

Updated three test files to reflect that `LeaseShellTransport.connect()` is now implemented (Phase 9):

1. **tests/test_transport.py**: Replaced `test_connect_raises_not_implemented` with `test_lease_shell_connect_opens_session` — patches TTY dependencies and verifies connect() doesn't raise NotImplementedError.

2. **tests/test_transport_cli_integration.py** (`TestTransportFlagParsed`): Updated `test_connect_accepts_transport_lease_shell` to assert `rc=0` and `mock_connect.called` instead of `rc=1`.

3. **tests/test_transport_cli_integration.py** (`TestLeaseShellStubBehaviour`): Replaced `test_connect_raises` with `test_connect_does_not_raise_not_implemented`.

4. **tests/test_lease_shell_exec.py** (`TestNotImplementedMethods`): Replaced `test_connect_not_implemented` with `test_connect_does_not_raise_not_implemented` (discovered during execution — not in original plan).

## Verification

- Full pytest suite: **475 passed, 0 failures**
- No NotImplementedError assertions on connect() remain in active tests

## Self-Check: PASSED
