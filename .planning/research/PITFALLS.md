# Domain Pitfalls: Adding Akash Lease-Shell WebSocket Transport to Just-Akash CLI

**Domain:** CLI tool adding WebSocket transport to existing SSH-based shell access on Akash Network

**Researched:** 2026-04-18

**Scope:** Common pitfalls when implementing lease-shell WebSocket transport in Python, migrating default transport from SSH to WebSocket, terminal lifecycle management, and WebSocket connection cleanup in CLI context.

**Overall Confidence:** MEDIUM
- Akash lease-shell architecture well-documented (HIGH)
- General Python WebSocket patterns documented (HIGH)
- Integration pitfalls and CLI-specific gotchas synthesized from patterns (MEDIUM)
- Specific Akash v1.5 pitfalls not yet in public issue tracking (LOW)

---

## Critical Pitfalls

### 1. Auth Token Expiry During Long Sessions

**What goes wrong:**
Lease-shell WebSocket connections use JWT authentication tokens with finite expiry (typically minutes to hours). Long-running interactive sessions crash when the token expires mid-session, with no built-in reconnection or token refresh mechanism.

**Why it happens:**
- Akash Console API issues bearer tokens with TTL (Time-To-Live)
- Client initiates WebSocket with initial token in URL or header
- Token becomes invalid after expiry period
- No standard WebSocket protocol for mid-stream re-authentication
- Naive implementation assumes static credentials for session lifetime

**Consequences:**
- User loses interactive shell access mid-command
- No graceful degradation (abrupt disconnect)
- Operations like `just-akash exec` or `just-akash inject` timeout unexpectedly
- Difficult to debug (looks like network timeout, not auth failure)

**Prevention:**
```python
# Anti-pattern: single token for session lifetime
async def connect_shell(dseq: str, token: str):
    async with websockets.connect(f"wss://...?token={token}") as ws:
        # Session dies if token expires before user finishes
        await interactive_shell_loop(ws)

# Pattern: token refresh wrapper
class WebSocketWithRefresh:
    def __init__(self, url: str, token_provider: Callable[[], str]):
        self.url = url
        self.token_provider = token_provider
        self.ws = None
        
    async def ensure_connected(self):
        """Verify connection, refresh token if needed"""
        if self.ws is None or self.ws.closed:
            token = self.token_provider()  # Get fresh token
            self.ws = await websockets.connect(
                self.url.replace("token=old", f"token={token}")
            )
    
    async def send(self, data):
        await self.ensure_connected()
        try:
            await self.ws.send(data)
        except websockets.exceptions.ConnectionClosed:
            # Reconnect on failure
            self.ws = None
            await self.ensure_connected()
            await self.ws.send(data)

# Operational: detect imminent expiry and warn user
def minutes_until_expiry(token: str) -> int:
    """Extract exp claim from JWT"""
    import base64, json, time
    parts = token.split(".")
    payload = json.loads(base64.b64decode(parts[1] + "=="))
    return int((payload["exp"] - time.time()) / 60)

async def shell_with_timeout_warning(ws, refresh_interval=5):
    """Warn user if token expires in <N minutes"""
    task = asyncio.create_task(interactive_shell_loop(ws))
    warning_task = asyncio.create_task(timeout_warning_loop(refresh_interval))
    # First to finish wins
    done, pending = await asyncio.wait(
        [task, warning_task],
        return_when=asyncio.FIRST_COMPLETED
    )
```

**Detection:**
- Interactive session suddenly closes with WebSocket close code 1000 (normal) but no graceful exit
- `ConnectionClosed` exceptions with status code during idle periods
- User reports "shell disconnects after ~30 minutes" (typical token TTL)
- Refresh token appears in implementation but not called

**Testing:**
```python
@pytest.mark.asyncio
async def test_token_expiry_mid_stream():
    # Simulate token expiring 5 seconds into session
    token_gen = iter([valid_token, valid_token, expired_token])
    
    async def mock_connect(url):
        token = next(token_gen)
        if token == expired_token:
            raise websockets.exceptions.InvalidStatusCode(401, "Unauthorized")
        return mock_ws
    
    # Ensure reconnection happens without user intervention
```

**Phase Responsibility:** v1.5-core (implementation); v1.5-hardening (token refresh)

**Akash-Specific Context:** Console API JWT tokens are short-lived by design. Clients must implement refresh, not assume session persistence.

---

### 2. TTY Raw Mode Leaking on Unclean Exit

**What goes wrong:**
Interactive shell mode sets terminal to raw mode (line buffering disabled, no signal processing). If the CLI crashes, gets killed (SIGKILL), or signal handler is interrupted, raw mode persists and terminal becomes unusable. User sees invisible input, no echo, broken shell behavior.

**Why it happens:**
- Python's `tty.setraw()` modifies kernel terminal state permanently until restored
- Exception/signal interruption bypasses cleanup code
- No context manager ensures `tty.setcooked()` on all exit paths
- Interactive mode detection (`sys.stdin.isatty()`) doesn't persist across async boundaries
- Signal handlers can themselves be interrupted before cleanup completes

**Consequences:**
- Terminal becomes unusable (no visible cursor, no input echo, no line editing)
- User forced to `reset` command or restart terminal
- Looks like application crash left terminal in broken state
- Reproducible but hard to diagnose (works fine normally, breaks under specific failure modes)

**Prevention:**
```python
import tty
import termios
import signal
import asyncio
from contextlib import asynccontextmanager

# Anti-pattern: manual save/restore in try/finally
def bad_interactive_shell(ws):
    if not sys.stdin.isatty():
        return  # Non-interactive, skip
    
    # Save state
    old_settings = termios.tcgetattr(sys.stdin)
    try:
        tty.setraw(sys.stdin.fileno())
        # Process commands
        # BUG: If exception here, old_settings never restored!
        while True:
            cmd = input("> ")
            ws.send(cmd)
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

# Pattern: asyncio-aware context manager with signal handlers
@asynccontextmanager
async def manage_interactive_terminal():
    """Guarantee TTY restoration on any exit path"""
    if not sys.stdin.isatty():
        yield
        return
    
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    
    # Restoration is critical: shield from cancellation
    try:
        tty.setraw(fd)
        
        # Signal handlers that trigger restoration
        original_sigint = signal.getsignal(signal.SIGINT)
        original_sigterm = signal.getsignal(signal.SIGTERM)
        
        def restore_and_exit(sig, frame):
            # Idempotent: safe to call multiple times
            try:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            except (OSError, ValueError):
                pass  # Already closed/restored
            if sig == signal.SIGINT:
                raise KeyboardInterrupt()
            else:
                sys.exit(128 + sig)
        
        signal.signal(signal.SIGINT, restore_and_exit)
        signal.signal(signal.SIGTERM, restore_and_exit)
        
        yield
    finally:
        # Restore synchronously (not awaited)
        # Use shield to prevent task cancellation interrupting this
        try:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        except (OSError, ValueError):
            pass  # fd already closed, acceptable
        finally:
            signal.signal(signal.SIGINT, original_sigint)
            signal.signal(signal.SIGTERM, original_sigterm)

# Usage in CLI
async def shell_command(dseq: str):
    async with manage_interactive_terminal():
        async with websockets.connect(url) as ws:
            await interactive_shell_loop(ws)

# Bonus: Detect if terminal is in raw mode (for testing)
def is_terminal_raw(fd=0) -> bool:
    """Check ICANON flag to detect raw vs cooked mode"""
    flags = termios.tcgetattr(fd)
    c_lflag = flags[3]  # c_lflag is index 3
    return not (c_lflag & termios.ICANON)
```

**Detection:**
- After crash/interrupt, user's shell has no echo, can't see cursor, line editing broken
- `is_terminal_raw()` check in tests confirms terminal state corruption
- Regression test that kills process mid-session and verifies cleanup
- CI/CD: Always verify stdin state after test suite completes

**Testing:**
```python
@pytest.mark.asyncio
async def test_tty_restored_on_signal():
    # Start interactive shell
    proc = subprocess.Popen([sys.executable, "-m", "just_akash", "shell", ...])
    await asyncio.sleep(0.5)  # Let shell start
    
    # Send SIGINT (Ctrl-C)
    proc.send_signal(signal.SIGINT)
    proc.wait(timeout=5)
    
    # Verify terminal is restored
    fd = sys.stdin.fileno()
    flags = termios.tcgetattr(fd)
    c_lflag = flags[3]
    assert c_lflag & termios.ICANON, "Terminal should be in cooked mode after cleanup"

@pytest.mark.asyncio
async def test_tty_restored_on_exception():
    """Verify TTY cleanup survives exceptions in shell loop"""
    with manage_interactive_terminal():
        raise ValueError("Simulated shell error")
    
    # If we reach here, cleanup happened despite exception
    assert not is_terminal_raw(), "Terminal must be cooked after context exit"
```

**Phase Responsibility:** v1.5-core (context manager); v1.5-test (signal handling tests)

**Linux/macOS Specific:** Different platforms handle terminal control slightly differently. Test on both Darwin and Linux.

---

### 3. Connection Teardown Race Conditions in Async Context

**What goes wrong:**
WebSocket close handshake is asynchronous. A CLI tool that exits immediately after initiating a close can leave the socket in CLOSE_WAIT state on the server. Multiple concurrent close attempts can deadlock or raise exceptions. Message send during close handshake fails unpredictably.

**Why it happens:**
- Python's `websockets` library uses async/await, requiring explicit `await`
- CLI code does `async with websockets.connect() as ws: ...` which auto-closes on exit
- But auto-close doesn't guarantee the close frame was *acknowledged*
- If CLI exits before ACK, OS leaves socket in TIME_WAIT/CLOSE_WAIT
- Multiple concurrent close handlers can race: both trying to send close frame

**Consequences:**
- Server sees socket in CLOSE_WAIT, leaking resources (file descriptors, memory)
- Subsequent deployments hit file descriptor limit, connection fails
- Command hangs on exit waiting for close handshake to complete
- `just-akash shell` leaves zombies, user has to kill process manually

**Prevention:**
```python
import asyncio
import websockets
from asyncio import TimeoutError as AsyncioTimeoutError

# Anti-pattern: fire-and-forget close
async def shell_bad():
    async with websockets.connect(url) as ws:
        await interactive_shell_loop(ws)
    # BUG: __aexit__ triggers close(), but doesn't wait for ACK from server
    # Connection may still be in CLOSE_WAIT on server side

# Pattern: explicit close with timeout
async def shell_good():
    ws = None
    try:
        ws = await websockets.connect(url)
        await interactive_shell_loop(ws)
    finally:
        if ws is not None and not ws.closed:
            try:
                # Close with explicit timeout to prevent hangs
                await asyncio.wait_for(ws.close(), timeout=5.0)
            except AsyncioTimeoutError:
                # Server didn't ACK close frame in time, force it
                ws.transport.close()
            except Exception:
                # Already closed or other error, acceptable
                pass

# Better pattern: shield close from cancellation
async def shell_robust():
    """Shell that guarantees clean close even under cancellation"""
    ws = None
    try:
        ws = await websockets.connect(url, close_timeout=10)
        await interactive_shell_loop(ws)
    finally:
        if ws is not None and not ws.closed:
            # Shield close from cancellation
            # (if main task is cancelled, close still happens)
            try:
                await asyncio.shield(ws.close())
            except Exception:
                # Force close if graceful close fails
                try:
                    ws.transport.close()
                except Exception:
                    pass

# Operational: detect zombie connections
class WebSocketWithCleanup:
    def __init__(self, url: str):
        self.url = url
        self.ws = None
        self.close_timeout = 10
        
    async def __aenter__(self):
        self.ws = await websockets.connect(self.url)
        return self.ws
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.ws and not self.ws.closed:
            try:
                # Explicit timeout prevents indefinite waits
                await asyncio.wait_for(
                    self.ws.close(),
                    timeout=self.close_timeout
                )
            except (AsyncioTimeoutError, websockets.exceptions.ConnectionClosed):
                # Timeout or already closed, acceptable outcomes
                if hasattr(self.ws, 'transport') and self.ws.transport:
                    self.ws.transport.close()
            except Exception as e:
                # Log unexpected errors but don't raise
                # (exception during exit is already being handled)
                print(f"Warning: error closing WebSocket: {e}")

# CLI usage
async def just_akash_shell(dseq: str):
    async with WebSocketWithCleanup(lease_shell_url(dseq)) as ws:
        await interactive_shell_loop(ws)
    # Guaranteed clean close before function returns
```

**Detection:**
- `netstat -an | grep CLOSE_WAIT` shows lingering sockets after script exit
- Test suite shows "too many open files" error after running many times
- Strace shows socket stays in CLOSE_WAIT state after `close()` syscall
- Integration test: launch 100 shell sessions, verify all close cleanly

**Testing:**
```python
@pytest.mark.asyncio
async def test_websocket_closes_gracefully():
    """Verify close handshake completes"""
    from unittest.mock import AsyncMock
    
    mock_ws = AsyncMock()
    mock_ws.closed = False
    mock_ws.close = AsyncMock()
    
    async with WebSocketWithCleanup("ws://test") as ws:
        # ws would be mock_ws in real test
        pass
    
    # Verify close was called and awaited
    mock_ws.close.assert_called_once()
    assert mock_ws.closed or mock_ws.close.awaited

@pytest.mark.asyncio
async def test_close_timeout_triggers_force_close():
    """Verify force close if server doesn't ACK"""
    from unittest.mock import AsyncMock, MagicMock
    
    mock_ws = AsyncMock()
    mock_ws.closed = False
    mock_ws.close = AsyncMock(side_effect=AsyncioTimeoutError())
    mock_ws.transport = MagicMock()
    
    try:
        async with WebSocketWithCleanup("ws://test") as ws:
            pass
    except:
        pass
    
    # Verify force close was attempted
    mock_ws.transport.close.assert_called()
```

**Phase Responsibility:** v1.5-core (context manager with timeout); v1.5-hardening (monitoring for leaks)

**Production Concern:** Under high load (many concurrent sessions), socket leak becomes critical. Monitor via `/proc/net/tcp` on Linux or `netstat` on macOS.

---

### 4. Binary Frame Parsing Errors in Terminal I/O

**What goes wrong:**
Lease-shell WebSocket endpoint sends terminal data (stdout/stderr) as binary frames. Naive text-only frame handling crashes on control characters, UTF-8 sequences, or binary data. Mixing text and binary handling creates undefined behavior.

**Why it happens:**
- WebSocket protocol supports both text (UTF-8 encoded) and binary frames
- Terminal data contains raw bytes (ANSI codes, binary output, non-UTF-8 sequences)
- Python's `websockets` library returns `str` for text frames, `bytes` for binary frames
- Code that assumes only text frames will crash on binary data
- Akash lease-shell endpoint sends frames as binary (spec depends on provider version)

**Consequences:**
- `UnicodeDecodeError` when terminal outputs non-UTF-8 bytes (e.g., file transfer, compiled output)
- AttributeError when code calls `.encode()` on bytes or `.decode()` on str inappropriately
- Data corruption when mixing text/binary handling (truncation, encoding confusion)
- Interactive shell becomes unusable if any command outputs binary data

**Prevention:**
```python
import asyncio
import websockets

# Anti-pattern: assume text-only frames
async def shell_bad(ws):
    while True:
        msg = await ws.recv()
        # BUG: msg could be bytes (binary frame)
        print(msg)  # Prints "b'\\x1b[...'" instead of rendered output

# Pattern: handle both text and binary frames uniformly
async def shell_good(ws):
    while True:
        msg = await ws.recv()
        
        # Normalize to bytes for consistent handling
        data = msg.encode() if isinstance(msg, str) else msg
        
        # Write to stdout as raw bytes (preserves control sequences)
        sys.stdout.buffer.write(data)
        sys.stdout.buffer.flush()

# Better: detect frame type and handle appropriately
async def shell_robust(ws):
    """Handle mixed text/binary frames from Akash lease-shell"""
    while True:
        try:
            msg = await ws.recv()
        except websockets.exceptions.ConnectionClosed:
            break
        
        # Determine frame type
        if isinstance(msg, bytes):
            # Binary frame: write directly to stdout (preserves all bytes)
            sys.stdout.buffer.write(msg)
        else:
            # Text frame: encode and write
            # (websockets already decoded as UTF-8)
            sys.stdout.buffer.write(msg.encode('utf-8', errors='replace'))
        
        sys.stdout.buffer.flush()

# Robust: handle encoding errors gracefully
async def safe_frame_handler(ws, output_file=None):
    """Handle frames with graceful error recovery"""
    if output_file is None:
        output_file = sys.stdout.buffer
    
    while True:
        try:
            msg = await ws.recv()
        except websockets.exceptions.ConnectionClosed:
            break
        except Exception as e:
            print(f"Error receiving frame: {e}", file=sys.stderr)
            continue
        
        try:
            if isinstance(msg, bytes):
                output_file.write(msg)
            else:
                # Encode text, replacing invalid UTF-8 sequences
                output_file.write(msg.encode('utf-8', errors='replace'))
            output_file.flush()
        except (BrokenPipeError, IOError):
            # Output pipe closed (e.g., piped to `head` and pipe closed)
            break
        except Exception as e:
            print(f"Error writing frame: {e}", file=sys.stderr)

# Testing-friendly version that separates I/O
async def receive_and_parse_frames(ws):
    """Generator that yields (is_binary: bool, data: bytes)"""
    while True:
        try:
            msg = await ws.recv()
        except websockets.exceptions.ConnectionClosed:
            break
        
        if isinstance(msg, bytes):
            yield (True, msg)
        else:
            yield (False, msg.encode('utf-8', errors='replace'))
```

**Detection:**
- `UnicodeDecodeError` in logs when binary data arrives
- Interactive shell works for simple commands but fails on `cat <binary_file>`
- Integration test: send ANSI control sequences (e.g., `echo -e "\x1b[31mRed\x1b[0m"`)
- Test with non-UTF-8 data: `dd if=/dev/urandom | head -c 100`

**Testing:**
```python
@pytest.mark.asyncio
async def test_binary_frame_handling():
    """Verify binary frames don't crash parser"""
    from io import BytesIO
    
    # Simulate Akash sending ANSI codes + binary data
    frames = [
        b"\x1b[31m",  # Red color code
        b"Error: ",
        b"\x1b[0m",   # Reset code
        b"\x00\xFF\xFE",  # Invalid UTF-8 bytes
    ]
    
    output = BytesIO()
    
    # Mock websocket that yields our test frames
    class MockWS:
        def __init__(self):
            self.frames = iter(frames)
        
        async def recv(self):
            return next(self.frames)
    
    # Should handle all frames without crashing
    frame_count = 0
    async for is_binary, data in receive_and_parse_frames(MockWS()):
        output.write(data)
        frame_count += 1
    
    assert frame_count == len(frames)
    # Verify output preserves binary data
    result = output.getvalue()
    assert result == b"\x1b[31mError: \x1b[0m\x00\xFF\xFE"

@pytest.mark.asyncio
async def test_text_frame_with_encoding_error():
    """Verify graceful handling of invalid UTF-8 in text frames"""
    # Websockets library converts binary to text (UTF-8)
    # If server sends invalid UTF-8, websockets may raise UnicodeDecodeError
    # Our handler must survive this
    
    # This requires monkeypatching websockets.recv() to raise
    # UnicodeDecodeError on specific calls
    pass
```

**Phase Responsibility:** v1.5-core (unified binary handling); v1.5-test (encoding edge cases)

**Akash-Specific:** Verify whether Console API sends text or binary frames. Spec may differ between provider versions.

---

### 5. Interactive vs Non-Interactive Mode Detection Breakage

**What goes wrong:**
The CLI detects interactive shell mode via `sys.stdin.isatty()`. But this detection can be incorrect in complex scenarios: piped input, redirected stdout, subprocess invocation, or Justfile context. Code branches differently for interactive/non-interactive, leading to hard-to-debug behavior.

**Why it happens:**
- `sys.stdin.isatty()` only checks stdin, not stdout/stderr
- Shell scripts often redirect one but not all streams
- Justfile execution context may change TTY status
- Different behavior between direct CLI invocation and `python -m just_akash`
- No consistent pattern for "what is interactive?" across command types

**Consequences:**
- `just-akash shell` shows non-interactive prompt when stdout is piped
- `just-akash exec` runs in wrong mode (interactive flags fail in non-interactive)
- User redirects output (`just-akash shell > output.txt`) and gets wrong behavior
- `just shell` (Justfile recipe) behaves differently than `just-akash shell` (CLI)

**Prevention:**
```python
import sys
import os

# Anti-pattern: single check, inconsistent across code
def is_interactive_bad():
    return sys.stdin.isatty()

# Pattern: explicit mode detection with documented fallback
def is_interactive_strict() -> bool:
    """True only if ALL of stdin/stdout/stderr are TTYs"""
    return (
        sys.stdin.isatty() and
        sys.stdout.isatty() and
        sys.stderr.isatty()
    )

def is_interactive_lenient() -> bool:
    """True if stdin is a TTY (user can interact, even if output is piped)"""
    return sys.stdin.isatty()

def is_interactive_forced() -> bool:
    """Allow override via environment variable"""
    # User can force: JUST_AKASH_INTERACTIVE=1 just-akash shell
    if os.environ.get("JUST_AKASH_INTERACTIVE") == "1":
        return True
    return sys.stdin.isatty()

# Better: mode is an explicit parameter, not auto-detected
async def shell_command(
    dseq: str,
    mode: Optional[str] = None  # "interactive", "non-interactive", or None for auto-detect
):
    """
    Execute interactive shell.
    
    mode: 
      - "interactive": Force interactive mode (TTY setup, signal handling)
      - "non-interactive": Force non-interactive (no TTY, batch mode)
      - None: Auto-detect based on sys.stdin.isatty()
    """
    
    if mode is None:
        interactive = sys.stdin.isatty()
    elif mode == "interactive":
        interactive = True
    elif mode == "non-interactive":
        interactive = False
    else:
        raise ValueError(f"Unknown mode: {mode}")
    
    if interactive:
        # Set up TTY, signal handlers, etc.
        async with manage_interactive_terminal():
            await shell_loop(dseq, interactive=True)
    else:
        # No TTY setup, simpler cleanup
        await shell_loop(dseq, interactive=False)

# Operational: log detected mode for debugging
async def shell_command_with_logging(dseq: str):
    interactive = sys.stdin.isatty()
    print(f"[DEBUG] Running in {'interactive' if interactive else 'non-interactive'} mode", 
          file=sys.stderr)
    print(f"[DEBUG] stdin.isatty()={sys.stdin.isatty()}, stdout.isatty()={sys.stdout.isatty()}, "
          f"stderr.isatty()={sys.stderr.isatty()}", file=sys.stderr)
    await shell_command(dseq)

# CLI integration: expose mode as flag
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["interactive", "non-interactive"],
                        help="Force interactive or non-interactive mode (default: auto-detect)")
    # ... other args ...
    args = parser.parse_args()
    
    asyncio.run(shell_command(args.dseq, mode=args.mode))
```

**Detection:**
- Test: run `just-akash shell < /dev/null` (no input) → should handle gracefully
- Test: run `just-akash shell > /tmp/output.txt` (redirected output) → verify mode is correct
- Test: run from Justfile with output captured → log actual mode, verify expectations
- Test: run with piped input `echo "ls" | just-akash exec` → should behave non-interactively

**Testing:**
```python
def test_interactive_detection_with_redirected_input(tmp_path):
    """Verify behavior when stdin is a pipe"""
    script = """
import sys
from just_akash.cli import is_interactive_lenient
print(is_interactive_lenient())
"""
    
    # Run with piped input (stdin not TTY)
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=b"",
        capture_output=True
    )
    
    # Should print False
    assert result.stdout.strip() == b"False"

def test_mode_flag_overrides_detection():
    """Verify --mode flag overrides auto-detection"""
    # Even with piped input, --mode=interactive should force interactive mode
    result = subprocess.run(
        ["just-akash", "shell", "--mode", "interactive", "--dseq", "123"],
        input=b"exit\n",  # Provide exit command
        capture_output=True,
        timeout=5
    )
    # Should not crash, should respect flag
    assert result.returncode in (0, 1)  # 0 success, 1 connection error (expected in test)
```

**Phase Responsibility:** v1.5-core (mode detection); v1.5-test (edge case coverage)

**Justfile Context:** The `justfile` may invoke CLI differently than direct CLI invocation. Test both paths.

---

## Moderate Pitfalls

### 6. Default Transport Migration Breaking SSH Users

**What goes wrong:**
Changing default transport from SSH → lease-shell breaks users with existing SSH workflows. Scripts, CI/CD, and documentation all expect SSH. When default changes, things silently behave differently (or fail).

**Why it happens:**
- Users have scripts like `just-akash exec "my command"` that implicitly use SSH
- v1.5 changes default to lease-shell
- No explicit `--transport ssh` flag in script
- Behavior differs: lease-shell may not support all SSH features (port forwarding, SCP, etc.)
- No deprecation period or migration guide

**Consequences:**
- Existing user scripts fail or behave unexpectedly
- CI/CD pipelines break silently
- Users blame the tool, not their scripts
- Migration path unclear

**Prevention:**
```python
# Explicit transport selection in CLI
def exec_command(command: str, transport: str = "lease-shell"):
    """
    Execute command on deployment.
    
    transport: "lease-shell" (default, WebSocket) or "ssh" (legacy)
    """
    if transport == "lease-shell":
        return exec_via_lease_shell(command)
    elif transport == "ssh":
        return exec_via_ssh(command)
    else:
        raise ValueError(f"Unknown transport: {transport}")

# CLI flag for explicit selection
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", default="lease-shell",
                        choices=["lease-shell", "ssh"],
                        help="Transport mechanism (default: lease-shell)")
    # ...

# Deprecation warning for SSH users
def check_ssh_flag_deprecated():
    """Warn if user is using old SSH flag"""
    import sys
    if "--ssh" in sys.argv or "-S" in sys.argv:
        print("[WARN] The --ssh flag is deprecated. Use --transport ssh instead.",
              file=sys.stderr)

# Documentation: add migration guide
MIGRATION_GUIDE = """
v1.5 Migration: Default Transport Changed to lease-shell
========================================================

If your scripts rely on SSH, update them:

OLD:
    just-akash exec "ls"  # Uses SSH by default

NEW:
    just-akash exec "ls"  # Uses lease-shell by default
    
    # To keep using SSH:
    just-akash exec --transport ssh "ls"

See docs/MIGRATION.md for details.
"""
```

**Detection:**
- Monitor error logs for SSH-specific errors (`host key verification`, `ssh: command not found`)
- Integration test: run suite with `export JUST_AKASH_TRANSPORT=ssh` to simulate old behavior
- Document breaking change prominently in CHANGELOG

**Phase Responsibility:** v1.5-core (add --transport flag); v1.5-release (migration guide)

**Testing:**
```python
def test_transport_flag_preserved():
    """Verify --transport flag is respected"""
    result = subprocess.run(
        ["just-akash", "exec", "--transport", "ssh", "--dseq", "123", "ls"],
        capture_output=True
    )
    # Should attempt SSH, not lease-shell
    # (May fail, but should try SSH path)

def test_default_transport_is_lease_shell():
    """Verify lease-shell is default"""
    # Inspect implementation, not output (output may vary by context)
    from just_akash.cli import exec_command
    # Verify signature has transport default
    sig = inspect.signature(exec_command)
    assert sig.parameters["transport"].default == "lease-shell"
```

---

### 7. Token Refresh Complexity and State Desynchronization

**What goes wrong:**
When implementing token refresh, state can get out of sync: pending messages during refresh, failed refresh while command is mid-execution, or session state lost after reconnect.

**Why it happens:**
- Refresh requires temporary disconnect, breaking the WebSocket stream
- Messages received before old token expires but after new token issued can get lost
- State machine becomes complex with multiple failure modes

**Prevention:**
- Implement message queue that survives reconnect
- Use refresh tokens instead of re-authenticating from scratch
- Test token expiry scenarios explicitly

**Phase Responsibility:** v1.5-hardening

---

### 8. Timeout Configuration Complexity

**What goes wrong:**
WebSocket has multiple timeout layers: open_timeout (handshake), close_timeout (close handshake), ping_timeout (keepalive). Different values can cause unexpected behavior: connections hang, timeouts trigger at wrong times, or cleanup takes too long.

**Why it happens:**
- Defaults may not match Akash provider network characteristics
- No consistent timeout strategy across commands
- Network conditions (latency, packet loss) affect which timeout fires

**Prevention:**
```python
# Consistent timeout configuration
WEBSOCKET_CONFIG = {
    "open_timeout": 10,      # Handshake must complete in 10 seconds
    "close_timeout": 5,      # Close must complete in 5 seconds
    "ping_interval": 20,     # Send keepalive every 20 seconds
    "ping_timeout": 10,      # Wait 10 seconds for pong response
}

async def connect_with_timeouts(url: str):
    return await websockets.connect(url, **WEBSOCKET_CONFIG)

# Document timeout strategy
TIMEOUT_STRATEGY = """
- open_timeout=10s: Akash Console API typically responds in <1s
- close_timeout=5s: Close handshake should be quick
- ping_interval=20s: Keep connection alive across NAT/firewall
- ping_timeout=10s: Detect dead connections in 10s
"""
```

**Phase Responsibility:** v1.5-hardening (tuning)

---

## Minor Pitfalls

### 9. Test Mocking Complexity for WebSocket Streams

**What goes wrong:**
Testing WebSocket code is harder than HTTP. Mock WebSocket connections must simulate realistic frame sequences, handle async iteration correctly, and support connection drops. Naive mocking misses real bugs.

**Why it happens:**
- WebSocket is bidirectional streaming, not request-response
- Mock must properly implement `async for` protocol
- Need to simulate connection failures, timeouts, binary data

**Prevention:**
```python
# Utility: realistic mock WebSocket for testing
class MockWebSocket:
    def __init__(self, frames):
        self.frames = iter(frames)
        self.closed = False
        self.sent = []
    
    async def recv(self):
        try:
            return next(self.frames)
        except StopIteration:
            self.closed = True
            raise websockets.exceptions.ConnectionClosed(None, None)
    
    async def send(self, data):
        self.sent.append(data)
    
    async def close(self):
        self.closed = True

# Use monkeypatch with fixture
@pytest.fixture
def mock_websocket_connect(monkeypatch):
    async def _connect(url, **kwargs):
        # Return appropriate mock based on URL
        if "shell" in url:
            return MockWebSocket([b"prompt> ", b"ls", b"\n", b"file1\nfile2\n"])
        return MockWebSocket([])
    
    monkeypatch.setattr("websockets.connect", _connect)
```

**Phase Responsibility:** v1.5-test

---

### 10. Leak Detection and Monitoring Gaps

**What goes wrong:**
Without monitoring, connection leaks, token refresh failures, and unclean shutdowns go unnoticed in production until they cause cascading failures.

**Why it happens:**
- Async code doesn't show errors as obviously as sync code
- Cleanup failures are silent by default
- No built-in metrics for WebSocket health

**Prevention:**
- Add metrics: active connections, failed refreshes, close timeouts, frame errors
- Log all error paths
- Instrument integration tests to detect leaks

**Phase Responsibility:** v1.5-hardening

---

## Phase-Specific Warnings

| Phase Topic | Likely Pitfall | Mitigation |
|-------------|---------------|------------|
| WebSocket transport implementation | Token expiry, binary frame handling | Implement refresh + test with binary data early |
| TTY mode setup | Raw mode not restored | Use context manager + signal handlers, test with interruption |
| Connection cleanup | Sockets linger in CLOSE_WAIT | Explicit close timeout, test with many sessions |
| Default transport change | SSH users' scripts break silently | Add --transport flag early, document migration path |
| Interactive mode detection | Broken when I/O is redirected | Explicit mode flag, log detected mode |
| Testing | Mocks miss real async bugs | Use realistic async mocks, test with real provider if possible |

---

## Research Gaps & Next Steps

**Areas needing deeper phase-specific research:**

1. **Exact Akash token TTL & refresh mechanism** — v1.5-core needs to know exact token lifetime and refresh API spec. Check Akash Console API documentation or provider-services source code.

2. **Provider-specific frame format** — Different provider versions may send text vs binary frames. Needs validation against real providers.

3. **SSH compatibility requirements** — Which SSH features must be preserved? Port forwarding, SCP, agent forwarding? Affects migration scope.

4. **Performance implications** — WebSocket overhead vs SSH. Throughput, latency, CPU usage. Relevant for `just inject` (large file transfer).

5. **Multiplexing strategy** — Multiple concurrent commands on single WebSocket vs separate connections. Impacts architecture.

---

## Summary for Roadmap

**Critical (v1.5-core):**
- Token refresh implementation with mid-stream handling
- TTY context manager with signal handlers
- WebSocket close with explicit timeout
- Binary frame handling (not text-only)
- Interactive/non-interactive mode flag

**Important (v1.5-hardening):**
- Token expiry monitoring and warnings
- Connection leak detection tests
- Comprehensive integration tests with real provider
- Performance benchmarking vs SSH
- Signal handling edge cases (SIGKILL, nested interrupts)

**Operational (v1.5-release):**
- Migration guide for SSH users
- --transport flag documentation
- Timeout tuning for Akash network characteristics
- Monitoring/metrics setup

---

## Sources

- [Akash Lease-Shell Issue #87](https://github.com/akash-network/support/issues/87) — Provider restart breaks lease-shell; context not updated
- [JWT Authentication for Provider API](https://akash.network/roadmap/aep-64/) — Token specification and refresh requirements
- [Deployment Shell Access - Akash Guidebook](https://docs.akash.network/features/deployment-shell-access) — Official lease-shell documentation
- [WebSocket Connection Lifecycle Management](https://oneuptime.com/blog/post/2026-02-03-python-websocket-clients/view) — Python WebSocket client patterns
- [Python Asyncio Context Managers](https://medium.com/@hitorunajp/asynchronous-context-managers-f1c33d38c9e3) — Cleanup patterns and pitfalls
- [WebSocket Token Refresh Strategies](https://ably.com/topic/websockets-python) — Token lifecycle and refresh mechanisms
- [Python TTY and Signal Handling](https://docs.python.org/3/library/tty.html) — Terminal control in Python
- [Interactive Mode Detection](https://www.pythonlore.com/working-with-os-isatty-for-terminal-detection-in-python/) — sys.stdin.isatty() patterns
- [websockets Library Documentation](https://websockets.readthedocs.io/) — Reference implementation and best practices
