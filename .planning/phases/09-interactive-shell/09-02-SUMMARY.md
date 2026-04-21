---
plan: 09-02
status: complete
tasks_completed: 3
tasks_total: 3
key_files:
  created: []
  modified:
    - just_akash/transport/lease_shell.py
---

# Plan 09-02: Implement LeaseShellTransport.connect()

## What Was Built

Full interactive TTY shell via lease-shell WebSocket. Three atomic commits:

1. **TTY setup, guards, terminal restoration**: Platform guard (win32), non-TTY guard, `tty.setraw`, try-finally with `termios.tcsetattr` unconditional restore (SHLL-04). Frame constants at module level.

2. **WebSocket setup, SIGINT/SIGWINCH handlers**: `_run_interactive_session()` builds WebSocket URL with `tty=true&stdin=true`, sends initial terminal resize frame (SHLL-02), installs SIGINT forwarder (bytes [104, 0x03], SHLL-03) and SIGWINCH resize handler with stored-size fallback.

3. **select() I/O loop**: `_run_io_loop()` multiplexes stdin→frame 104 and frames 100/101/102 dispatch to stdout/stderr/exit (SHLL-01). Catches `TimeoutError` only (not generic Exception) to avoid swallowing test stop signals.

## Notable Deviations

- `_make_transport()` in test file updated to include mock API client and config (required for `_fetch_jwt()` to work in test context without network).
- SIGWINCH handler uses stored `_last_size` fallback when `os.get_terminal_size()` fails (handles test calling handler after patch context exits).
- `capture_signal` in SIGINT/SIGWINCH tests updated to only capture callable handlers (not `SIG_DFL`) to avoid overwrite on signal restore.
- `except Exception: pass` narrowed to `except TimeoutError: pass` to prevent infinite loops in mock test scenarios.

## Verification

- pytest tests/test_interactive_shell.py: **14/14 PASSED**
- pytest tests/test_transport.py tests/test_transport_cli_integration.py: 2 expected failures (test_connect_raises_not_implemented, test_connect_raises) — addressed in Plan 09-03

## Self-Check: PASSED
