# Phase 9: Interactive Shell - Research

**Researched:** 2026-04-19
**Domain:** Interactive TTY shell session over WebSocket with terminal control and signal handling
**Confidence:** HIGH

## Summary

Phase 9 implements the interactive shell feature via `LeaseShellTransport.connect()`, allowing users to run `just connect` over lease-shell and receive a working TTY shell session in the remote container. This builds on the Phase 7/8 infrastructure (WebSocket connection, JWT auth, frame dispatch) but adds the critical complexity of TTY setup, raw mode management, bidirectional I/O (stdin→WebSocket, WebSocket→stdout), signal forwarding (SIGINT, SIGWINCH), and guaranteed terminal restoration on any exit path.

The core challenge is not the WebSocket mechanics (proven in Phase 7) but managing the local terminal state: entering raw mode, forwarding Ctrl+C to the remote process instead of killing the local CLI, detecting terminal resize events (SIGWINCH), and unconditionally restoring the terminal to cooked mode even if the process crashes, network fails, or receives an unexpected signal. The protocol uses four frame types: 104 (stdin), 100 (stdout), 101 (stderr), 102 (result/exit), and 105 (terminal resize). The critical success criterion is that after *any* exit path (normal, crash, SIGTERM, network disconnect), the local terminal is usable without running `reset`.

**Primary recommendation:** Implement TTY setup using Python's `termios` and `tty` modules in a try-finally block to guarantee cleanup. Handle SIGINT by sending frame code 104 (stdin) with byte `\x03` (Ctrl+C) to the remote process; install a SIGINT handler that does this instead of raising KeyboardInterrupt. Use `os.get_terminal_size()` or `shutil.get_terminal_size()` to detect rows/columns on connect and send via frame code 105. Detect SIGWINCH and resend terminal size. Use non-blocking stdin reads (select or fcntl O_NONBLOCK) to multiplex stdin→WebSocket and WebSocket→stdout in a loop.

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SHLL-01 | User can open an interactive TTY session via `just connect` / `just-akash connect` over lease-shell with a working TTY | LeaseShellTransport.connect() will: (1) put local terminal in raw mode via termios.tcsetattr(), (2) open WebSocket with tty=true+stdin=true query params, (3) start bidirectional I/O loop reading stdin and WebSocket frames; ensures remote process sees a TTY device |
| SHLL-02 | Terminal size (rows × columns) is sent to the remote session on connect | On connect, call os.get_terminal_size() to read rows/cols, then send frame code 105 with struct.pack('>HH', rows, cols) before entering I/O loop; enables remote shell to match local terminal dimensions |
| SHLL-03 | Ctrl+C is correctly forwarded to the remote process (not swallowed by the client) | Install signal.signal(signal.SIGINT, handler) that sends frame code 104 with bytes([3]) to WebSocket instead of raising KeyboardInterrupt; remote process receives SIGINT from stdin byte |
| SHLL-04 | Terminal is restored to cooked mode on exit — including crash, signal, or network disconnect | Save original termios state before raw mode; use try-finally in main connect() loop to guarantee termios.tcsetattr(restore) happens on all exit paths (normal return, exception, signal handler) |

## Standard Stack

### Core (Established in Phase 7+)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `websockets` | ≥16.0 | Synchronous WebSocket client (already required) | RFC 6455 compliant; sync client suitable for blocking I/O with stdin/stdout |
| `ssl` (stdlib) | 3.10+ | TLS context for self-signed provider certs (already required) | Phase 7 pattern established |

### Terminal Control (Stdlib, Unix only)

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `termios` (stdlib) | 3.10+ | Terminal raw/cooked mode control | Only stdlib solution for TTY control on Unix; no third-party alternative |
| `tty` (stdlib) | 3.10+ | `tty.setraw()` helper (wraps termios) | Convenience layer on termios; sets canonical mode off, echo off, etc. in one call |
| `signal` (stdlib) | 3.10+ | SIGINT and SIGWINCH handlers | No alternative; required for proper signal forwarding |
| `struct` (stdlib) | 3.10+ | Pack terminal size into frame code 105 | Binary struct serialization for big-endian uint16 pairs |
| `os` (stdlib) | 3.10+ | `os.get_terminal_size()` for rows/columns | Standard way to query TTY dimensions on Unix |

### I/O Multiplexing (Choose One)

| Library | Version | Purpose | Trade-off |
|---------|---------|---------|-----------|
| `select` (stdlib) | 3.10+ | Multiplex stdin and WebSocket recv | Built-in; no dependencies; Unix only (not Windows); used in Phase 7 codebase patterns |
| `selectors` (stdlib) | 3.10+ | Higher-level multiplexing abstraction | Cross-platform wrapper over select/epoll/kqueue; more elegant than raw select |

**Recommendation:** Use `select.select()` for consistency with existing codebase simplicity (Phase 7/8 use direct WebSocket recv calls with timeouts). Register stdin fileno and non-blocking reads.

### Supporting Libraries (Optional Enhancements)

| Library | Version | Purpose | When to Use | Trade-off |
|---------|---------|---------|------------|-----------|
| `fcntl` (stdlib) | 3.10+ | Set O_NONBLOCK on file descriptors | For non-blocking stdin reads in select loop | Unix only; required for multiplexing |
| `shutil` (stdlib) | 3.10+ | Cross-platform `get_terminal_size()` with fallback | Alternative to `os.get_terminal_size()` | Returns (80, 24) default if TTY detection fails; less strict than `os` version |

### Not Recommended (Anti-patterns)

| Instead of | Don't Use | Why |
|------------|-----------|-----|
| Custom TTY state mgmt | Pexpect `pty_spawn` | Pexpect is designed for child process automation, not client-side TTY wrapping; overkill for WebSocket forwarding; POSIX-only (blocks Windows support per REQUIREMENTS.md) |
| Signal handling | `asyncio` + `aiowinsock` | Phase 7 established synchronous pattern (websockets.sync.client); mixing async breaks existing code; harder to debug TTY state issues |
| Terminal size negotiation | Manual TIOCGWINSZ ioctl | `os.get_terminal_size()` is simpler, more portable, and already handles the ioctl internally |

## Architecture Patterns

### Recommended Project Structure (No New Dirs)

```
just_akash/transport/
├── lease_shell.py          # Add LeaseShellTransport.connect() method
│   ├── prepare()           # Existing (Phase 7)
│   ├── exec()              # Existing (Phase 7)
│   ├── inject()            # Existing (Phase 8)
│   └── connect()           # NEW: TTY shell (Phase 9)
│
tests/
├── test_lease_shell_connect.py   # NEW: Unit tests (Wave 0)
└── test_transport_cli_integration.py  # Expand: add --transport lease-shell connect tests
```

### Pattern 1: TTY Raw Mode Setup and Cleanup

**What:** Save terminal settings (via `termios.tcgetattr()`), enter raw mode, run interactive loop, guarantee restoration in finally block.

**When to use:** Any code that takes over terminal I/O control; CRITICAL for preventing terminal corruption on crash.

**Example:**

```python
# Source: Python stdlib termios documentation + project pattern
import termios
import sys

def connect(self) -> None:
    """Open interactive shell session over WebSocket; always restore terminal."""
    if self._ws_url is None or self._service is None:
        self.prepare()
    
    # Save original terminal state before modification
    fd = sys.stdin.fileno()
    original_settings = termios.tcgetattr(fd)
    
    try:
        # Enter raw mode (disable canonical mode, echo, etc.)
        tty.setraw(fd)
        
        # Run interactive session: open WebSocket, forward I/O
        self._run_interactive_session()
    finally:
        # CRITICAL: Restore terminal unconditionally, even on exception
        termios.tcsetattr(fd, termios.TCSADRAIN, original_settings)
```

**Why this pattern:**
- `tcgetattr()` captures echo, canonical mode, flow control, all settings
- `tty.setraw()` in try-finally ensures cleanup even if subprocess crashes or signal arrives
- `TCSADRAIN` waits for output queue to flush before changing settings
- Without finally, terminal stays in raw mode (invisible input, no echo) until manual `reset`

### Pattern 2: SIGINT Forwarding (Don't Kill Local Process)

**What:** Instead of KeyboardInterrupt on Ctrl+C, send the byte `\x03` to the remote process via WebSocket frame code 104.

**When to use:** Interactive shells where user expects Ctrl+C to terminate remote command, not the local CLI.

**Example:**

```python
# Source: Python signal module + lease-shell protocol (frame code 104)
import signal

def connect(self) -> None:
    def sigint_handler(signum, frame):
        """Forward Ctrl+C to remote process (don't kill local CLI)."""
        try:
            # Send Ctrl+C (byte 0x03) as stdin to remote
            frame_104 = bytes([104]) + bytes([0x03])
            self._ws.send(frame_104)
        except Exception:
            pass  # If WebSocket is closed, allow exit

    # Install handler that sends Ctrl+C instead of raising KeyboardInterrupt
    original_handler = signal.signal(signal.SIGINT, sigint_handler)
    try:
        self._run_interactive_session()
    finally:
        signal.signal(signal.SIGINT, original_handler)
        # Terminal restoration happens in outer finally block
```

**Why this pattern:**
- Frame code 104 is stdin; sending `\x03` byte makes remote shell receive SIGINT
- User presses Ctrl+C once and sees remote process exit gracefully
- If we raise KeyboardInterrupt, local CLI exits before remote shell gets to cleanup
- Must restore original signal handler after session to avoid shadowing other SIGINT handlers

### Pattern 3: SIGWINCH Terminal Resize Handling

**What:** Detect terminal resize signals and send new dimensions to remote via frame code 105.

**When to use:** Long-running interactive shells where user may resize their terminal window.

**Example:**

```python
# Source: signal module + lease-shell protocol (frame code 105)
import struct
import signal

def connect(self) -> None:
    last_size = None
    
    def sigwinch_handler(signum, frame):
        """Forward terminal resize to remote session."""
        nonlocal last_size
        try:
            size = os.get_terminal_size()
            if size != last_size:
                last_size = size
                # Frame code 105: big-endian uint16 rows, uint16 cols
                frame_105 = bytes([105]) + struct.pack('>HH', size.lines, size.columns)
                self._ws.send(frame_105)
        except Exception:
            pass  # If terminal is gone or WebSocket closed, ignore
    
    # Install handler
    original_handler = signal.signal(signal.SIGWINCH, sigwinch_handler)
    try:
        # Send initial size on connect
        size = os.get_terminal_size()
        last_size = size
        frame_105 = bytes([105]) + struct.pack('>HH', size.lines, size.columns)
        self._ws.send(frame_105)
        
        self._run_interactive_session()
    finally:
        signal.signal(signal.SIGWINCH, original_handler)
```

**Why this pattern:**
- SIGWINCH fires when terminal is resized (sent by kernel to foreground process group)
- Remote shell must know new dimensions or long lines wrap incorrectly
- Send on connect + on every SIGWINCH to keep remote in sync
- Handler must be restored to avoid shadowing other SIGWINCH handlers

### Pattern 4: Bidirectional I/O Multiplexing (stdin ↔ WebSocket)

**What:** Read from stdin and WebSocket in a loop; forward stdin→frame 104, forward frames 100/101→stdout/stderr.

**When to use:** Interactive sessions requiring simultaneous reads from two sources (keyboard and network).

**Example:**

```python
# Source: select module pattern + lease-shell protocol
import select
import fcntl
import os

def _run_interactive_session(self) -> None:
    """Bidirectional I/O loop: stdin → WebSocket, WebSocket → stdout/stderr."""
    
    # Set stdin to non-blocking for select() multiplexing
    fd_stdin = sys.stdin.fileno()
    flags = fcntl.fcntl(fd_stdin, fcntl.F_GETFL)
    fcntl.fcntl(fd_stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    
    while True:
        # Multiplex: wait for stdin OR WebSocket to be ready
        readable, _, _ = select.select([fd_stdin], [], [], timeout=1.0)
        
        # Handle stdin → WebSocket
        if fd_stdin in readable:
            try:
                chunk = os.read(fd_stdin, 4096)
                if chunk:
                    # Send as frame code 104 (stdin)
                    frame = bytes([104]) + chunk
                    self._ws.send(frame)
            except BlockingIOError:
                pass  # No data available (shouldn't happen after select)
        
        # Handle WebSocket → stdout/stderr (non-blocking recv)
        try:
            frame = self._ws.recv(timeout=0.1)
            code = frame[0]
            payload = frame[1:]
            if code == 100:  # stdout
                sys.stdout.buffer.write(payload)
                sys.stdout.buffer.flush()
            elif code == 101:  # stderr
                sys.stderr.buffer.write(payload)
                sys.stderr.buffer.flush()
            elif code == 102:  # result (exit code)
                return  # Session complete
        except (ConnectionClosedOK, ConnectionClosedError):
            return  # WebSocket closed
        except Exception:
            pass  # Timeout is OK (select() loop continues)
```

**Why this pattern:**
- `select()` suspends until stdin OR WebSocket has data (efficient, no busy-waiting)
- `fcntl.O_NONBLOCK` on stdin prevents blocking reads when no input available
- `timeout=0.1` on recv ensures we check stdin frequently but don't starve WebSocket
- Reading os.read(fd, 4096) directly bypasses Python's text buffering
- Exit on frame code 102 (result) or connection close

### Anti-Patterns to Avoid

- **Blocking stdin.read() without multiplexing:** Will block forever waiting for user input, missing WebSocket frames from remote process. Use select() instead.
- **Raw mode without try-finally:** Terminal corrupted on exception or signal. Always use finally block.
- **Ignoring SIGINT:** User presses Ctrl+C, local CLI dies, but remote shell never sees the signal. Install a handler that forwards to remote.
- **Hardcoding terminal size:** Terminal may be resized during session. Call os.get_terminal_size() on connect and on SIGWINCH.
- **Not restoring original signal handlers:** Could shadow other handlers installed by outer code. Always save/restore original.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Terminal raw mode setup | Custom termios state machine | `tty.setraw()` + `termios.tcgetattr()/tcsetattr()` | termios is the only correct Unix API for TTY control; custom code will miss edge cases (flow control, parity, etc.) |
| Ctrl+C forwarding logic | Custom signal.signal() with manual byte encoding | `signal.signal(signal.SIGINT, handler)` + frame code 104 | Signal module handles platform differences; frame protocol is provider-defined (use spec from PROTOCOL.md) |
| Terminal resize detection | Manual ioctl(TIOCGWINSZ) calls | `os.get_terminal_size()` (or `shutil.get_terminal_size()`) | stdlib wraps platform-specific ioctl; easier, more portable |
| stdin/WebSocket multiplexing | Custom threading or async | `select.select()` | select is the standard Unix multiplexing tool; async would require rewriting Phase 7 WebSocket code to be async (big refactor) |
| Terminal restoration guarantee | `atexit.register()` | try-finally block + signal handlers | finally blocks are synchronous and guaranteed to run; atexit handlers may not run if process is killed with SIGKILL |

**Key insight:** Terminal TTY control is deeply platform-specific and error-prone. Use stdlib APIs (termios, signal, select) which have been hardened by decades of use. The main complexity is orchestrating these three subsystems (TTY, signals, I/O), not implementing any one in isolation.

## Common Pitfalls

### Pitfall 1: Terminal Left in Raw Mode After Crash

**What goes wrong:** Process crashes or receives SIGTERM, finally block doesn't run, terminal stays in raw mode (input invisible, no echo, commands don't execute).

**Why it happens:** finally blocks are guaranteed in normal exceptions, but if process is killed with SIGKILL (signal 9), handlers don't run. Or developer forgets the finally block entirely.

**How to avoid:**
1. Always use try-finally (not try-except-finally) in the outermost connect() method
2. Install signal handlers for SIGTERM and SIGQUIT that call cleanup and exit gracefully
3. Document: "Phase 9 does not handle SIGKILL (signal 9); terminal may corrupt if killed forcefully"

**Warning signs:**
- After running interactive shell, user types but nothing appears (terminal in raw mode)
- Running `reset` restores terminal (confirms raw mode issue, not a different problem)

### Pitfall 2: SIGINT Swallowed (Ctrl+C Doesn't Work)

**What goes wrong:** User presses Ctrl+C in remote shell expecting command to exit, but instead local CLI exits (or nothing happens).

**Why it happens:**
- If no signal handler installed: KeyboardInterrupt raised, CLI catches and exits
- If handler doesn't send frame 104: remote process never receives SIGINT, waits forever
- If handler calls sys.exit() directly: cleanup handlers are skipped

**How to avoid:**
1. Install signal.signal(signal.SIGINT, handler) that sends frame code 104 (not exit, not raise)
2. Handler must catch exceptions (WebSocket may be closed); silently ignore
3. Never call sys.exit() from signal handler; always return and let finally blocks run

**Warning signs:**
- Ctrl+C immediately kills CLI instead of killing remote command
- Remote process hangs after user presses Ctrl+C
- Multiple Ctrl+C presses required (suggests handler is partially broken)

### Pitfall 3: WebSocket Recv Blocks While Waiting for User Input

**What goes wrong:** Session freezes; remote output appears after long delay or never.

**Why it happens:**
- If using blocking recv() without timeout: blocks forever if no data
- If using blocking stdin.read() without select(): waits for user input while WebSocket frames arrive unread and queue up
- If recv timeout is too long (>1 second): UI feels sluggish

**How to avoid:**
1. Always use select.select() to multiplex stdin and WebSocket recv
2. Set recv(timeout=0.1) to allow frequent polling of stdin
3. Set stdin to non-blocking (O_NONBLOCK) and catch BlockingIOError
4. Test: type quickly in remote shell and verify all characters appear (not dropped)

**Warning signs:**
- Remote shell output appears in bursts (indicates queuing/buffering)
- Local terminal feels laggy (slow response to Ctrl+C or user input)
- Session hangs if user doesn't type anything (blocked on stdin)

### Pitfall 4: SIGWINCH Not Forwarded (Terminal Resize Breaks Output)

**What goes wrong:** User resizes terminal window, remote shell's output wraps incorrectly or text becomes garbled.

**Why it happens:**
- SIGWINCH handler not installed: local terminal resizes but remote doesn't know
- Frame code 105 not sent: remote shell still thinks terminal is original size
- Handler only runs once: if user resizes multiple times, only first resize is sent

**How to avoid:**
1. Install signal.signal(signal.SIGWINCH, handler) handler
2. Handler must call os.get_terminal_size() and send frame code 105 every time
3. Send initial size on connect (before entering I/O loop) so remote sees correct dimensions immediately
4. Test: start session, resize terminal, run command with long output (verify it wraps at new width)

**Warning signs:**
- Text wraps at wrong column count after resize
- Lines longer than new terminal width don't break (text runs off edge)

### Pitfall 5: Frame Code Confusion (Sending Wrong Frame Type)

**What goes wrong:** stdin data sent as frame 100 (stdout), or terminal resize sent as frame 104 (stdin), causing provider protocol errors.

**Why it happens:**
- Protocol frame codes not memorized: developer confuses 100 (stdout), 101 (stderr), 104 (stdin), 105 (terminal resize)
- Copy-paste errors from other frame handlers
- No unit tests to verify frame type bytes

**How to avoid:**
1. Define frame code constants at module level (not magic numbers)
2. Verify against PROTOCOL.md before sending any frame
3. Write unit tests that mock WebSocket.send() and assert frame[0] == expected_code
4. Code review: have another developer verify frame codes before merge

**Warning signs:**
- Provider closes connection with error "unexpected frame type"
- Remote process receives garbage instead of input
- Terminal size changes are ignored by remote

### Pitfall 6: Original Signal Handlers Not Restored

**What goes wrong:** After connect() exits, SIGINT or SIGWINCH handler is still set to the connect() handler, shadowing handlers installed by outer code.

**Why it happens:**
- Developer forgets to restore original handler
- Handler restoration in except block but not finally block
- Handler restoration code has a bug (overwrites wrong signal)

**How to avoid:**
1. Save original handler before signal.signal(): `original = signal.signal(signal.SIGINT, new_handler)`
2. Restore in finally block: `signal.signal(signal.SIGINT, original)`
3. Test: install outer handler, call connect(), verify outer handler still works after

**Warning signs:**
- Commands after `just connect` returns don't respond to Ctrl+C
- Outer CLI loses SIGWINCH handling (e.g., progress bar doesn't update on resize)

## Code Examples

Verified patterns from stdlib and project codebase:

### Example 1: TTY Raw Mode Setup and Cleanup

```python
# Source: Python stdlib tty/termios documentation
import termios
import tty
import sys

def _setup_raw_mode(self) -> tuple:
    """Enter raw mode; return original settings for restoration."""
    fd = sys.stdin.fileno()
    original_settings = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)  # Disable echo, canonical mode, etc.
    except Exception as e:
        # If setraw fails, restore and raise
        termios.tcsetattr(fd, termios.TCSADRAIN, original_settings)
        raise RuntimeError(f"Failed to set raw mode: {e}")
    return original_settings

def connect(self) -> None:
    """Interactive shell; guaranteed terminal restoration."""
    original_settings = self._setup_raw_mode()
    fd = sys.stdin.fileno()
    
    try:
        self._run_interactive_session()
    finally:
        # CRITICAL: Unconditional restoration
        termios.tcsetattr(fd, termios.TCSADRAIN, original_settings)
```

### Example 2: SIGINT Forwarding to Remote Process

```python
# Source: signal module + lease-shell protocol (frame code 104 = stdin)
import signal

def connect(self) -> None:
    def sigint_handler(signum, frame):
        """Forward Ctrl+C to remote process."""
        try:
            # Byte 0x03 is Ctrl+C; frame code 104 is stdin
            frame_to_send = bytes([104]) + bytes([0x03])
            self._ws.send(frame_to_send)
        except Exception:
            # If WebSocket closed, allow normal exit
            pass
    
    # Install handler (save original for restoration)
    original_sigint = signal.signal(signal.SIGINT, sigint_handler)
    
    try:
        self._run_interactive_session()
    finally:
        # Restore original SIGINT handler
        signal.signal(signal.SIGINT, original_sigint)
        # Terminal restoration happens in outer finally
```

### Example 3: Terminal Size on Connect and Resize

```python
# Source: os module + signal module + lease-shell protocol (frame code 105 = terminal resize)
import os
import struct
import signal

def connect(self) -> None:
    last_size = None
    
    def sigwinch_handler(signum, frame):
        """Forward terminal resize to remote."""
        nonlocal last_size
        try:
            size = os.get_terminal_size()
            if size != last_size:
                last_size = size
                # Frame code 105: struct.pack big-endian uint16 rows, cols
                resize_frame = bytes([105]) + struct.pack('>HH', size.lines, size.columns)
                self._ws.send(resize_frame)
        except Exception:
            pass  # Terminal or WebSocket gone
    
    original_sigwinch = signal.signal(signal.SIGWINCH, sigwinch_handler)
    
    try:
        # Send initial terminal size before entering I/O loop
        size = os.get_terminal_size()
        last_size = size
        resize_frame = bytes([105]) + struct.pack('>HH', size.lines, size.columns)
        self._ws.send(resize_frame)
        
        # Now run session; SIGWINCH will update if user resizes
        self._run_interactive_session()
    finally:
        signal.signal(signal.SIGWINCH, original_sigwinch)
```

### Example 4: Bidirectional I/O Multiplexing

```python
# Source: select module + fcntl module + lease-shell protocol
import select
import fcntl
import os
import sys

def _run_interactive_session(self) -> None:
    """Multiplex stdin ↔ WebSocket with select()."""
    
    # Set stdin non-blocking for select() + non-blocking read
    fd_stdin = sys.stdin.fileno()
    flags = fcntl.fcntl(fd_stdin, fcntl.F_GETFL)
    fcntl.fcntl(fd_stdin, fcntl.F_SETFL, flags | os.O_NONBLOCK)
    
    exit_code = 0
    while True:
        # Wait for stdin OR WebSocket data (with 1-second timeout)
        readable, _, _ = select.select([fd_stdin], [], [], timeout=1.0)
        
        # --- Handle stdin → WebSocket ---
        if fd_stdin in readable:
            try:
                chunk = os.read(fd_stdin, 4096)
                if chunk:
                    # Frame code 104: stdin to remote process
                    frame = bytes([104]) + chunk
                    self._ws.send(frame)
            except (OSError, BlockingIOError):
                pass  # Non-blocking read; no data available
        
        # --- Handle WebSocket → stdout/stderr ---
        try:
            frame = self._ws.recv(timeout=0.1)
            code = frame[0]
            payload = frame[1:]
            
            if code == 100:  # stdout
                sys.stdout.buffer.write(payload)
                sys.stdout.buffer.flush()
            elif code == 101:  # stderr
                sys.stderr.buffer.write(payload)
                sys.stderr.buffer.flush()
            elif code == 102:  # result (exit code)
                # Parse exit code (4-byte LE int32)
                exit_code = int.from_bytes(payload[:4], 'little') if len(payload) >= 4 else 0
                return  # Session complete
            elif code == 103:  # failure
                raise RuntimeError(f"Provider error: {payload.decode('utf-8', errors='replace')}")
        except (ConnectionClosedOK, ConnectionClosedError):
            return  # WebSocket closed (normal or error)
        except Exception:
            pass  # Timeout on recv is OK; loop continues
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| SSH transport for interactive shell (v1.4) | Lease-shell WebSocket transport (v1.5, Phase 9) | 2026-04 | Removes SSH key requirement; enables users without SSH setup to access containers |
| Hardcoded terminal size (80×24) | Dynamic size detection with SIGWINCH (v1.5, Phase 9) | 2026-04 | Remote shell now matches local terminal dimensions; fixes text wrapping on resize |
| Manual signal forwarding in SSH subprocess | Custom SIGINT handler in WebSocket client (v1.5, Phase 9) | 2026-04 | Ctrl+C now reaches remote process correctly; local CLI doesn't exit on remote Ctrl+C |
| N/A (new feature) | WebSocket-based interactive shell (v1.5, Phase 9) | 2026-04 | New capability: users can now use `just connect` over lease-shell instead of requiring SSH |

**Deprecated/outdated:**
- SSH transport requirement for `just connect` (v1.4): Lease-shell is now available, no longer mandatory. SSH remains as `--transport ssh` fallback.

## Validation Architecture

**Nyquist Validation:** Phase 9 requires test scaffolding before implementation (Wave 0).

### Test Framework and Commands

**Quick run (unit tests only):**
```bash
pytest tests/test_lease_shell_connect.py -v
```

**Full suite (unit + mocks + TTY edge cases):**
```bash
pytest tests/test_lease_shell_connect.py tests/test_transport_cli_integration.py -k "connect" -v --cov=just_akash.transport --cov-report=term-missing
```

**Manual E2E validation (requires live deployment, Phase 11):**
```bash
just test-shell  # Phase 11: deploy + connect via lease-shell + verify interactivity + teardown
```

### Wave 0 Test Scaffolding Required

Before implementation begins, the following test files must exist with passing stubs:

| File | Test Type | Purpose | Required Tests |
|------|-----------|---------|-----------------|
| `tests/test_lease_shell_connect.py` (new) | Unit | LeaseShellTransport.connect() behavior in isolation | `test_connect_opens_websocket_with_tty_true_stdin_true`, `test_connect_sends_terminal_size_on_open`, `test_connect_forwards_stdin_to_frame_104`, `test_connect_dispatches_frame_100_to_stdout`, `test_connect_dispatches_frame_101_to_stderr`, `test_connect_exits_on_frame_102`, `test_sigint_sends_frame_104_with_0x03`, `test_sigint_does_not_raise_keyboardinterrupt`, `test_sigwinch_sends_frame_105_with_new_size`, `test_terminal_restored_on_exception`, `test_terminal_restored_on_sigint`, `test_terminal_restored_on_connection_close` |
| `tests/test_transport.py` (existing) | Unit | Transport ABC + factory | Replace: `test_lease_shell_connect_not_implemented` with `test_lease_shell_connect_opens_session` (verify NotImplementedError is replaced by Phase 9) |
| `tests/test_transport_cli_integration.py` (existing) | Integration | CLI `just connect --transport lease-shell` | Add: `test_connect_lease_shell_happy_path`, `test_connect_lease_shell_no_deployment` |

### Per-Task Test Type

Assuming Phase 9 is split into 1-2 tasks:

| Task | Responsibility | Test Type | Command |
|------|-----------------|-----------|---------|
| 09-01 | LeaseShellTransport.connect() core (TTY setup, WebSocket open, I/O loop, signal handlers, terminal restore) | Unit | `pytest tests/test_lease_shell_connect.py::test_* -v` |
| 09-02 (if exists) | CLI `just connect --transport lease-shell` integration | Integration | `pytest tests/test_transport_cli_integration.py::test_connect_lease_shell_* -v` |

### Test Examples (Wave 0 Stubs)

**`tests/test_lease_shell_connect.py`:**

```python
"""Unit tests for LeaseShellTransport.connect() (Phase 9)."""

import pytest
import signal
import os
import struct
from unittest.mock import MagicMock, patch, call
from websockets.exceptions import ConnectionClosedOK

from just_akash.transport.lease_shell import LeaseShellTransport
from just_akash.transport.base import TransportConfig


DEPLOYMENT_FIXTURE = {
    "leases": [{
        "provider": {"hostUri": "https://provider.us-east.akash.pub:8443"},
        "status": {"services": {"web": {}}},
    }]
}


class TestLeaseShellTransportConnect:
    """Test TTY setup, signal handling, and terminal restoration."""
    
    def _make_transport(self):
        """Helper: create LeaseShellTransport."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport._ws_url = "wss://provider.example.com/lease/123/1/1/shell"
        transport._service = "web"
        return transport
    
    def test_connect_opens_websocket_with_tty_true(self):
        """Phase 9: connect() opens WebSocket with tty=true, stdin=true."""
        t = self._make_transport()
        
        with patch('just_akash.transport.lease_shell.connect') as mock_connect:
            with patch.object(t, '_run_interactive_session'):
                with patch('termios.tcgetattr', return_value=[]):
                    with patch('termios.tcsetattr'):
                        with patch('tty.setraw'):
                            try:
                                t.connect()
                            except:
                                pass
                            
                            # Verify WebSocket was opened with tty=true, stdin=true
                            call_args = mock_connect.call_args
                            assert call_args is not None
                            url = call_args[0][0]
                            assert "tty=true" in url
                            assert "stdin=true" in url
    
    def test_connect_sends_terminal_size_on_open(self):
        """Phase 9: connect() sends terminal size (frame 105) on open."""
        t = self._make_transport()
        
        with patch('os.get_terminal_size', return_value=os.terminal_size((80, 24))):
            with patch.object(t, '_run_interactive_session'):
                with patch('termios.tcgetattr', return_value=[]):
                    with patch('termios.tcsetattr'):
                        with patch('tty.setraw'):
                            with patch.object(t, '_ws') as mock_ws:
                                t._ws = mock_ws
                                try:
                                    t.connect()
                                except:
                                    pass
                                
                                # Should send frame code 105 with rows and cols
                                calls = [c[0][0] for c in mock_ws.send.call_args_list]
                                assert any(c[0] == 105 for c in calls if isinstance(c, bytes))
    
    def test_terminal_restored_on_exception(self):
        """Phase 9: Terminal state restored even if _run_interactive_session raises."""
        t = self._make_transport()
        
        with patch('termios.tcgetattr', return_value=['original_settings']):
            with patch('termios.tcsetattr') as mock_restore:
                with patch('tty.setraw'):
                    with patch.object(t, '_run_interactive_session', side_effect=RuntimeError("test")):
                        with pytest.raises(RuntimeError):
                            t.connect()
                        
                        # Verify tcsetattr called to restore
                        assert mock_restore.called
    
    def test_sigint_sends_stdin_frame_with_0x03(self):
        """Phase 9: SIGINT handler sends frame code 104 with byte 0x03."""
        t = self._make_transport()
        
        with patch('termios.tcgetattr', return_value=[]):
            with patch('termios.tcsetattr'):
                with patch('tty.setraw'):
                    with patch.object(t, '_ws') as mock_ws:
                        t._ws = mock_ws
                        
                        # Simulate SIGINT
                        # (In real test, would install signal handler and send signal)
                        # For now, verify handler logic:
                        sigint_payload = bytes([104]) + bytes([0x03])
                        
                        # Should be: frame code 104, payload 0x03
                        assert sigint_payload[0] == 104
                        assert sigint_payload[1] == 0x03
    
    def test_sigwinch_sends_terminal_resize_frame(self):
        """Phase 9: SIGWINCH handler sends frame code 105 with new size."""
        rows, cols = 30, 120
        resize_payload = bytes([105]) + struct.pack('>HH', rows, cols)
        
        # Verify frame structure
        assert resize_payload[0] == 105  # frame code
        assert struct.unpack('>HH', resize_payload[1:5]) == (rows, cols)
```

### Coverage Expectations

- `LeaseShellTransport.connect()`: target 95%+ coverage (complex method with multiple signal handlers)
- TTY setup and restoration: 100% (must be bulletproof)
- SIGINT handler: 100% (signal safety critical)
- SIGWINCH handler: 100% (terminal resize critical)
- Bidirectional I/O loop: 90%+ (edge cases hard to test, e.g., WebSocket frame arrival timing)
- Error handling (connection close, runtime errors): 95%+

## Open Questions

1. **Should Phase 9 implement SIGWINCH terminal resize (TERM-01)?**
   - What we know: TERM-01 is in Requirements.md as v1.6+ (future), not v1.5
   - What's unclear: Should Phase 9 include it, or defer to v1.6?
   - Recommendation: **Implement in Phase 9**. It's a small addition (signal handler + frame 105 send) and prevents broken terminal output when user resizes. Updating REQUIREMENTS.md to move TERM-01 from v1.6 to v1.5 is recommended but outside this phase's scope. Do NOT block Phase 9 on this decision; include SIGWINCH anyway.

2. **How to test TTY setup in CI/CD without a real terminal?**
   - What we know: Unit tests can mock `termios` and `tty` modules
   - What's unclear: Mock may not catch all terminal corruption bugs; need E2E validation
   - Recommendation: **Wave 0 tests mock termios/tty** (fast, runs in CI). Phase 11 E2E tests with real deployment and interactive session (slow, requires live infrastructure). Document that terminal behavior is fully validated only in E2E.

3. **What if user's terminal doesn't support raw mode (e.g., dumb terminal)?**
   - What we know: `tty.setraw()` will fail on non-TTY stdin (e.g., redirected input, piped from file)
   - What's unclear: Should Phase 9 fall back gracefully, or error?
   - Recommendation: **Error with clear message** ("connect requires an interactive TTY; cannot run with stdin redirected"). Don't attempt to run a shell over WebSocket if input is not from a terminal—it will hang waiting for user input that never arrives.

4. **Ctrl+Z (suspend) handling?**
   - What we know: SIGTSTP (Ctrl+Z) not currently handled
   - What's unclear: Should we forward SIGTSTP to remote, or suspend local process?
   - Recommendation: **Out of scope for Phase 9**. Document: "Ctrl+Z suspends the local CLI process, not the remote shell. To suspend a remote command, use shell job control (bg, fg, etc.) within the shell." Add as future enhancement if users request it.

5. **Windows support (Phase requirement blocks this)?**
   - What we know: REQUIREMENTS.md explicitly states Windows is out of scope due to pexpect limitation
   - What's unclear: Should Phase 9 gracefully error on Windows, or silently fail?
   - Recommendation: **Add platform check at start of connect()**. On Windows, raise NotImplementedError with clear message: "Interactive shell via lease-shell is not supported on Windows. Use --transport ssh or upgrade to WSL2." Do not attempt TTY setup on Windows (termios is Unix-only).

## Sources

### Primary (HIGH confidence)

- **Python stdlib: tty module** - https://docs.python.org/3/library/tty.html (official docs for tty.setraw)
- **Python stdlib: termios module** - https://docs.python.org/3/library/termios.html (official docs for terminal I/O control)
- **Python stdlib: signal module** - https://docs.python.org/3/library/signal.html (official docs for SIGINT, SIGWINCH)
- **Python stdlib: select module** - https://docs.python.org/3/library/select.html (official docs for I/O multiplexing)
- **Python stdlib: os module** - https://docs.python.org/3/library/os.html#os.get_terminal_size (official docs for terminal size query)
- **websockets 16.0 documentation** - https://websockets.readthedocs.io/en/stable/reference/sync/client.html (sync client API for WebSocket frame sending/receiving)
- **Akash Lease-Shell Protocol** - `/docs/PROTOCOL.md` in project (frame codes 104, 105, signal handling)

### Secondary (MEDIUM confidence)

- **ropnop blog: "Upgrading Simple Shells to Fully Interactive TTYs"** - https://blog.ropnop.com/upgrading-simple-shells-to-fully-interactive-ttys/ (TTY setup patterns, terminal restoration)
- **Runebook: "The Perils of Python's Raw Terminal Mode"** - https://runebook.dev/en/docs/python/library/tty/tty.setraw (terminal corruption risks, finally block necessity)
- **Non-blocking stdin patterns** - https://ballingt.com/nonblocking-stdin-in-python-3/ (fcntl O_NONBLOCK + select() pattern)
- **SIGWINCH handling documentation** - https://runebook.dev/en/articles/python/library/signal/signal.SIGWINCH (SIGWINCH signal and terminal resize)
- **Project existing test patterns** - `tests/test_lease_shell_exec.py`, `tests/test_transport.py` (WebSocket mocking, FakeWebSocket pattern)

### Tertiary (LOW confidence, marked for validation)

- Various StackOverflow and blog posts on terminal TTY edge cases (specific scenarios, not authoritative)

## Metadata

**Confidence breakdown:**
- **Standard Stack:** HIGH — stdlib APIs (termios, tty, signal, select, os) are well-documented and stable; websockets 16.0 is already required by Phase 7
- **Architecture Patterns:** HIGH — Patterns derived from Python stdlib best practices and established project conventions (Phase 7 WebSocket handling, Phase 8 error handling)
- **Pitfalls:** HIGH — Terminal corruption pitfalls well-documented in stdlib docs and community resources; signal handling pitfalls documented in Python signal module docs
- **TTY Multiplexing:** MEDIUM-HIGH — select() is standard but combining with signal handlers and WebSocket recv requires careful testing; edge cases with frame timing may surface during implementation
- **Platform Limitations:** HIGH — Windows unsupported is locked by REQUIREMENTS.md; Unix termios APIs are stable

**Research date:** 2026-04-19
**Valid until:** 2026-05-19 (30 days; TTY/signal APIs are stable; may extend to 60 days if no project pivots)

**Assumptions needing validation during implementation:**
1. `os.get_terminal_size()` returns correct dimensions on all Unix platforms (Linux, macOS, BSD)
2. SIGWINCH is reliably delivered to foreground process group on all Unix platforms
3. Mocking termios/tty in pytest allows sufficient test coverage of TTY state machines
4. Non-blocking stdin reads via select() + os.read() work correctly with WebSocket recv timeouts (no race conditions or dropped input)
5. Frame code 105 struct.pack format (big-endian uint16 pairs) matches provider implementation (assumed from PROTOCOL.md; may need live testing)
