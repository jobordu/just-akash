---
phase: "09"
status: passed
verified_at: "2026-04-19"
requirements: [SHLL-01, SHLL-02, SHLL-03, SHLL-04]
formal_check: null
---

# Phase 09: Interactive Shell — Verification

## Goal Verification

**Goal**: Users can open a full interactive TTY shell session over lease-shell; the terminal is always restored cleanly regardless of how the session ends.

**Result**: PASSED — all four success criteria met.

## Must-Haves

### SC-1: `just connect` opens an interactive shell session over lease-shell with a working TTY

**Status**: PASSED

**Evidence**:
- `LeaseShellTransport.connect()` implemented in `just_akash/transport/lease_shell.py`
- `tty.setraw(fd)` called after platform and TTY guards
- WebSocket opened with `tty=true&stdin=true` query params
- `test_connect_opens_websocket_with_tty_true_stdin_true` PASSED — `mock_ws.call_args[0][0]` contains `tty=true` and `stdin=true`
- CLI integration: `test_connect_accepts_transport_lease_shell` asserts `rc=0` and `mock_connect.called`

### SC-2: Remote session receives correct terminal dimensions (rows × columns) on connect

**Status**: PASSED

**Evidence**:
- `os.get_terminal_size()` called at session start; result packed as `struct.pack(">HH", size.lines, size.columns)` prefixed with `_FRAME_RESIZE` (105)
- `test_connect_sends_terminal_size_on_connect` PASSED — verifies frame[0]==105, rows==24, cols==80
- SIGWINCH handler sends updated dimensions on terminal resize

### SC-3: Ctrl+C forwards interrupt to remote process (does not terminate local CLI)

**Status**: PASSED

**Evidence**:
- `signal.signal(signal.SIGINT, _sigint_handler)` registered in `_run_interactive_session()`
- `_sigint_handler` sends `bytes([_FRAME_STDIN, 0x03])` via WebSocket
- `test_sigint_sends_frame_104_with_0x03` PASSED — handler sends `bytes([104, 0x03])`
- `test_sigint_does_not_raise_keyboardinterrupt` PASSED — connect() returns cleanly

### SC-4: Terminal restored to cooked mode on exit (crash, signal, network disconnect)

**Status**: PASSED

**Evidence**:
- `connect()` uses try-finally with `termios.tcsetattr(fd, termios.TCSADRAIN, original_settings)`
- Two finally blocks: outer in `connect()` (terminal restore), inner in `_run_interactive_session()` (signal restore, fcntl reset)
- `test_terminal_restored_on_normal_exit` PASSED
- `test_terminal_restored_on_exception` PASSED
- `test_terminal_restored_on_connection_close` PASSED

## Requirements Traceability

| Requirement | Description | Status |
|-------------|-------------|--------|
| SHLL-01 | Interactive TTY session via `just connect` over lease-shell | PASSED |
| SHLL-02 | Terminal size (rows × columns) sent to remote on connect | PASSED |
| SHLL-03 | Ctrl+C forwarded to remote process (not swallowed) | PASSED |
| SHLL-04 | Terminal restored to cooked mode on all exit paths | PASSED |

## Test Suite

- `tests/test_interactive_shell.py`: **14/14 PASSED**
- `tests/test_transport.py`: All PASSED (replaced stub assertion with positive test)
- `tests/test_transport_cli_integration.py`: All PASSED (rc=0, mock_connect.called)
- Full suite: **475/475 PASSED, 0 failures**

## Files Modified

- `just_akash/transport/lease_shell.py` — `connect()`, `_run_interactive_session()`, `_run_io_loop()`, frame constants
- `tests/test_interactive_shell.py` — created (Wave 0 stubs, all turn green)
- `tests/test_transport.py` — `test_lease_shell_connect_opens_session` replaces stub assertion
- `tests/test_transport_cli_integration.py` — updated two tests for Phase 9 reality
- `tests/test_lease_shell_exec.py` — updated one test for Phase 9 reality

## Formal Check

SKIPPED — no `.planning/formal/spec` directory exists for this project.
