---
plan: 08-01
phase: 08-secrets-injection-via-lease-shell
status: complete
completed_at: 2026-04-19
commits:
  - ea22163  # test(08-01): add failing tests for LeaseShellTransport.inject()
  - fac878d  # feat(08-01): implement LeaseShellTransport.inject() via exec() (INJS-01, INJS-02)
requirements_satisfied: [INJS-01, INJS-02]
---

# Plan 08-01: LeaseShellTransport.inject() — Secrets Injection via Lease Shell

## What Was Built

Implemented `LeaseShellTransport.inject(remote_path, content)` using three `exec()` calls:
1. `mkdir -p $(dirname <quoted_path>)` — ensure parent directory exists
2. `echo <base64_encoded> | base64 -d > <quoted_path>` — write content via base64 decode
3. `chmod 600 <quoted_path>` — restrict file permissions to owner only

Both `remote_path` is shell-quoted via `shlex.quote()` to prevent injection. Content is base64-encoded in transit so secret values never appear as plaintext in CLI output.

## Approach

TDD (Red-Green):
- **RED commit**: `test(08-01)` — 11 failing tests in `tests/test_transport_inject.py`, updated stubs in `test_transport.py` and `test_transport_cli_integration.py`
- **GREEN commit**: `feat(08-01)` — full implementation replacing `NotImplementedError` stub

## Key Files

- `just_akash/transport/lease_shell.py` — added `import base64`, `import shlex`; replaced stub with working `inject()`
- `tests/test_transport_inject.py` — 11 unit tests (new file)
- `tests/test_transport.py` — `test_inject_raises_not_implemented` → `test_lease_shell_inject_not_a_stub`
- `tests/test_transport_cli_integration.py` — `test_inject_accepts_transport_lease_shell` updated to assert `rc == 0`
- `tests/test_lease_shell_exec.py` — `test_inject_not_implemented` updated to `test_inject_implemented_phase_8`

## Test Results

- 11 new tests in `tests/test_transport_inject.py`: all pass
- Full suite: **461 passed, 0 failed** (was 450 before this plan)
- INJS-02 verified: `test_inject_secret_value_not_in_exec_command_plaintext` passes

## Requirements Satisfied

- **INJS-01**: `just inject --transport lease-shell` writes secrets without SSH keys or port 22 — exec() uses JWT auth over WebSocket only
- **INJS-02**: Secret values never appear in CLI stdout — base64 encoding means exec() commands contain only the encoded string, never plaintext; `echo | base64 -d > path` redirect produces no terminal output

## Issues Encountered

None. Both TDD cycles completed cleanly. One additional test in `test_lease_shell_exec.py` (from Phase 7) also required updating from expecting `NotImplementedError` to verifying the implemented behavior.

## Self-Check: PASSED
