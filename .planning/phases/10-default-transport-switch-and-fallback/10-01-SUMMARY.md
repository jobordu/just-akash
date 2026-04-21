---
phase: 10-default-transport-switch-and-fallback
plan: "01"
status: complete
completed_at: "2026-04-19"
tasks_completed: 2
tests_added: 9
tests_red: 8
tests_green: 1
---

# Plan 10-01 Summary: Wave 0 TDD Stubs

## What Was Built

Created `tests/test_default_transport.py` with 9 test functions establishing the Phase 10
behavioral contract before any implementation changes.

## Test Results

- `pytest tests/test_default_transport.py`: 8 FAILED, 1 PASSED (expected — RED/GREEN state)
- `pytest --ignore=tests/test_default_transport.py`: 475 PASSED, 0 failures (no regression)

## RED Tests (8 — define implementation contract)

| Class | Test | What it asserts |
|-------|------|----------------|
| TestDefaultTransportArgparse | test_exec_defaults_to_lease_shell | exec with no --transport calls LeaseShellTransport.exec() |
| TestDefaultTransportArgparse | test_inject_defaults_to_lease_shell | inject with no --transport calls LeaseShellTransport.inject() |
| TestDefaultTransportArgparse | test_connect_defaults_to_lease_shell | connect with no --transport calls LeaseShellTransport.connect() |
| TestFallbackToSSH | test_exec_fallback_to_ssh_when_validate_false | stderr contains fallback notice when validate()=False |
| TestFallbackToSSH | test_inject_fallback_to_ssh_when_validate_false | stderr contains fallback notice when validate()=False |
| TestFallbackToSSH | test_connect_fallback_to_ssh_when_validate_false | os.execvp called + fallback notice on stderr |
| TestNoSshMsg | test_no_ssh_msg_does_not_claim_lease_shell_unsupported | NO_SSH_MSG lacks "does not support lease-shell" |
| TestExplicitSSHTransport | (PASSED — already satisfied) | |

## GREEN Test (1 — already satisfied by current code)

- `test_exec_ssh_transport_flag_bypasses_lease_shell`: `--transport ssh` forces SSH without calling validate()

## Key Files

- `tests/test_default_transport.py` (created, 224 lines)

## Commits

- `b4eb403` — test(10-01): add Wave 0 RED test stubs for default transport switch
