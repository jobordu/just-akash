"""
Lease-shell WebSocket transport (Phase 7).

Implements non-interactive command execution over the Akash provider WebSocket
using a JWT bearer token obtained from the Console API.

Protocol reference: docs/PROTOCOL.md
"""

from __future__ import annotations

import base64
import fcntl
import json
import os
import select
import shlex
import signal
import ssl
import struct
import sys
import termios
import tty
import urllib.parse
from typing import TYPE_CHECKING

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.sync.client import connect

from just_akash.api import AkashConsoleAPI

from .base import Transport, TransportConfig


# ------------------------------------------------------------------
# Module-level constants and helpers
# ------------------------------------------------------------------

MAX_RECONNECT_ATTEMPTS = 3

# Frame codes for lease-shell WebSocket protocol
_FRAME_STDOUT = 100       # Remote stdout
_FRAME_STDERR = 101       # Remote stderr
_FRAME_RESULT = 102       # Remote exit code
_FRAME_FAILURE = 103      # Provider error
_FRAME_STDIN = 104        # Client stdin to remote
_FRAME_RESIZE = 105       # Client terminal resize (big-endian uint16 rows, uint16 cols)


def _is_auth_expiry_message(msg: str) -> bool:
    """Return True if message text indicates auth expiry."""
    lower = msg.lower()
    return "expired" in lower or "unauthorized" in lower or "token" in lower


def _is_auth_expiry(exc: ConnectionClosedError) -> bool:
    """Return True if close event indicates JWT expiry or auth failure."""
    rcvd = getattr(exc, "rcvd", None)
    if rcvd is not None:
        code = getattr(rcvd, "code", None)
        if code in (4001, 4003):
            return True
        reason = getattr(rcvd, "reason", "") or ""
        if _is_auth_expiry_message(reason):
            return True
    # Fallback: check exception string representation
    return _is_auth_expiry_message(str(exc))


class LeaseShellTransport(Transport):
    """
    WebSocket-based lease-shell transport.

    Phase 7: implements prepare() + exec().
    Phase 8-9: implements inject() + connect().
    """

    def __init__(self, config: TransportConfig) -> None:
        self._config = config
        self._ws_url: str | None = None
        self._service: str | None = None
        self._api_client: AkashConsoleAPI | None = None

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_api_client(self) -> AkashConsoleAPI:
        if self._api_client is None:
            self._api_client = AkashConsoleAPI(
                api_key=self._config.api_key,
                base_url=self._config.console_url,
            )
        return self._api_client

    def _fetch_jwt(self, ttl: int = 3600) -> str:
        """Fetch a JWT from the Console API for the configured dseq."""
        return self._get_api_client().create_jwt(self._config.dseq, ttl=ttl)

    def _extract_provider_url(self) -> tuple[str, str]:
        """Return (ws_base_url, service_name) from deployment data.

        Raises RuntimeError if provider hostUri or service name cannot be determined.
        """
        leases = self._config.deployment.get("leases", [])
        if not leases or not isinstance(leases, list):
            raise RuntimeError(
                f"No leases found for deployment {self._config.dseq}. "
                "The deployment may not have an active lease yet."
            )
        lease = leases[0]
        if not isinstance(lease, dict):
            raise RuntimeError("Unexpected lease entry format in deployment data.")
        provider = lease.get("provider", {})
        if not isinstance(provider, dict):
            raise RuntimeError("Unexpected provider format in lease data.")
        # Console API may use either 'hostUri' or 'host_uri'
        host_uri: str | None = provider.get("hostUri") or provider.get("host_uri")
        if not host_uri:
            raise RuntimeError(
                "Provider hostUri not found in deployment lease data. "
                f"Available provider keys: {list(provider.keys())}"
            )
        # Convert https:// → wss://, http:// → ws://
        ws_base = host_uri.replace("https://", "wss://").replace("http://", "ws://")

        # Determine service name: config override or infer from deployment
        service = self._config.service_name or self._infer_service()
        if not service:
            raise RuntimeError(
                "Cannot determine service name. Pass service_name in TransportConfig "
                "or ensure deployment has an active service in lease status."
            )
        return ws_base, service

    def _infer_service(self) -> str | None:
        """Infer the first service name from deployment lease status."""
        leases = self._config.deployment.get("leases", [])
        if not leases:
            return None
        lease = leases[0] if isinstance(leases, list) else {}
        status = lease.get("status", {}) if isinstance(lease, dict) else {}
        services = status.get("services", {}) if isinstance(status, dict) else {}
        if isinstance(services, dict) and services:
            return next(iter(services))
        return None

    @staticmethod
    def _make_ssl_context() -> ssl.SSLContext:
        """TLS context that accepts self-signed provider certs (Phase 7)."""
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE  # providers use self-signed certs
        return ctx

    @staticmethod
    def _dispatch_frame(frame: bytes) -> int | None:
        """Dispatch a binary frame; write output, return exit code or None.

        Code 100: stdout — write to sys.stdout.buffer (unbuffered).
        Code 101: stderr — write to sys.stderr.buffer (unbuffered).
        Code 102: result — parse exit code (4-byte LE int32 or JSON fallback).
        Code 103: failure — raise RuntimeError with provider message.
        """
        if not isinstance(frame, bytes) or len(frame) < 1:
            return None
        code = frame[0]
        payload = frame[1:]
        if code == 100:  # stdout
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
        elif code == 101:  # stderr
            sys.stderr.buffer.write(payload)
            sys.stderr.buffer.flush()
        elif code == 102:  # result
            if len(payload) >= 4:
                try:
                    return int.from_bytes(payload[:4], "little")
                except (ValueError, OverflowError):
                    pass
            try:
                return int(json.loads(payload).get("exit_code", 0))
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
            return 0
        elif code == 103:  # failure
            msg = payload.decode("utf-8", errors="replace")
            raise RuntimeError(f"Provider error: {msg}")
        return None

    def _exec_with_refresh(self, command: str) -> int:
        """Execute command with automatic JWT refresh on token expiry.

        On ConnectionClosedError with auth close code (4001/4003) or 'expired'/'unauthorized'
        in reason, fetches a new JWT and reopens the connection. Repeats up to
        MAX_RECONNECT_ATTEMPTS times. Accumulated stdout/stderr already written
        to sys.stdout.buffer/sys.stderr.buffer — nothing is replayed.

        Returns the remote command exit code or raises RuntimeError if reconnection fails.
        """
        attempts = 0
        exit_code = 0

        while attempts < MAX_RECONNECT_ATTEMPTS:
            jwt = self._fetch_jwt()
            params = urllib.parse.urlencode({
                "cmd": command,
                "service": self._service,
                "tty": "false",
                "stdin": "false",
            })
            url = f"{self._ws_url}?{params}"
            headers = {"Authorization": f"Bearer {jwt}"}
            ssl_ctx = self._make_ssl_context()

            try:
                with connect(
                    url,
                    additional_headers=headers,
                    ssl=ssl_ctx,
                    compression=None,
                    open_timeout=30,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    while True:
                        try:
                            frame = ws.recv(timeout=300)
                        except ConnectionClosedOK:
                            return exit_code
                        except ConnectionClosedError as exc:
                            if _is_auth_expiry(exc):
                                break  # retry outer loop
                            raise  # non-auth close: propagate
                        result = self._dispatch_frame(frame)
                        if result is not None:
                            return result  # exit code received: done
            except RuntimeError as exc:
                if _is_auth_expiry_message(str(exc)):
                    pass  # fall through to retry
                else:
                    raise
            attempts += 1

        raise RuntimeError(
            f"Failed to re-authenticate after {MAX_RECONNECT_ATTEMPTS} attempts. "
            "Check that AKASH_API_KEY is valid and the deployment is active."
        )

    # ------------------------------------------------------------------
    # Transport interface
    # ------------------------------------------------------------------

    def prepare(self) -> None:
        """Validate transport: extract provider URL and service name.

        Sets self._ws_url and self._service.
        Raises RuntimeError if deployment has no active lease or provider URI.
        """
        ws_base, service = self._extract_provider_url()
        dseq = self._config.dseq
        self._ws_url = f"{ws_base}/lease/{dseq}/1/1/shell"
        self._service = service

    def exec(self, command: str) -> int:
        """Execute command on provider via lease-shell WebSocket; return exit code.

        Connects with a JWT bearer token, dispatches frames until result (102)
        or close event, then returns the remote exit code.

        If the provider closes due to JWT expiry (close codes 4001/4003 or reason
        containing 'expired'/'unauthorized'), automatically fetches a fresh token
        and retries the connection. Output already streamed to stdout/stderr is
        not replayed.

        Uses websockets.sync.client (NOT asyncio) — Transport.exec() is synchronous.
        compression=None: disable permessage-deflate (provider compatibility).
        """
        if self._ws_url is None or self._service is None:
            self.prepare()

        return self._exec_with_refresh(command)

    def inject(self, remote_path: str, content: str) -> None:
        """Write content to remote_path on the container via three exec() calls.

        Uses base64 encoding to safely transmit any UTF-8 content (handles
        newlines, quotes, backslashes without shell escaping issues).
        Path is shell-quoted via shlex.quote() to prevent injection.

        Secret values are never written to CLI stdout: the echo | base64 -d > path
        command redirects output into the file; the terminal receives nothing.
        """
        if self._ws_url is None or self._service is None:
            self.prepare()

        # Step 1: ensure parent directory exists
        mkdir_cmd = f"mkdir -p $(dirname {shlex.quote(remote_path)})"
        rc = self.exec(mkdir_cmd)
        if rc != 0:
            raise RuntimeError(
                f"Failed to create directory for {remote_path}: exit {rc}"
            )

        # Step 2: write content via base64 decode (plain text never appears in command)
        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        write_cmd = (
            f"echo {shlex.quote(encoded)} | base64 -d > {shlex.quote(remote_path)}"
        )
        rc = self.exec(write_cmd)
        if rc != 0:
            raise RuntimeError(f"Failed to write {remote_path}: exit {rc}")

        # Step 3: restrict permissions to owner-only
        chmod_cmd = f"chmod 600 {shlex.quote(remote_path)}"
        rc = self.exec(chmod_cmd)
        if rc != 0:
            raise RuntimeError(
                f"Failed to set permissions on {remote_path}: exit {rc}"
            )

    def connect(self) -> None:
        """Open interactive TTY shell session over lease-shell WebSocket.

        Enters raw mode, opens WebSocket with tty=true+stdin=true, sends initial
        terminal dimensions (SHLL-02), installs SIGINT forwarder (SHLL-03) and
        SIGWINCH resize handler, runs bidirectional I/O loop, then unconditionally
        restores terminal to cooked mode (SHLL-04).
        """
        if sys.platform == "win32":
            raise NotImplementedError(
                "Interactive shell via lease-shell is not supported on Windows. "
                "Use --transport ssh or run under WSL2."
            )
        if not sys.stdin.isatty():
            raise RuntimeError(
                "connect() requires an interactive TTY; stdin is not a terminal. "
                "Cannot run interactive shell with stdin redirected."
            )
        if self._ws_url is None or self._service is None:
            self.prepare()

        fd = sys.stdin.fileno()
        original_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            self._run_interactive_session()
        finally:
            # SHLL-04: Unconditional terminal restoration — must run even on crash/signal
            termios.tcsetattr(fd, termios.TCSADRAIN, original_settings)

    def _run_interactive_session(self) -> None:
        """Bidirectional I/O loop with signal forwarding and terminal resize.

        Opens WebSocket with tty=true&stdin=true, sends initial terminal size,
        installs SIGINT/SIGWINCH handlers, then multiplexes stdin<->WebSocket
        via select() until frame 102 (exit) or connection close.

        Signal handlers are restored in the finally block.
        Non-blocking stdin is reset to blocking in the finally block.
        """
        # --- Build WebSocket URL with tty=true, stdin=true (SHLL-01) ---
        jwt = self._fetch_jwt()
        params = urllib.parse.urlencode({
            "service": self._service,
            "tty": "true",
            "stdin": "true",
        })
        url = f"{self._ws_url}?{params}"
        headers = {"Authorization": f"Bearer {jwt}"}
        ssl_ctx = self._make_ssl_context()

        with connect(
            url,
            additional_headers=headers,
            ssl=ssl_ctx,
            compression=None,
            open_timeout=30,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            self._ws = ws

            # --- Send initial terminal dimensions (SHLL-02) ---
            try:
                size = os.get_terminal_size()
                resize_frame = bytes([_FRAME_RESIZE]) + struct.pack(">HH", size.lines, size.columns)
                ws.send(resize_frame)
            except OSError:
                pass  # Non-TTY fallback: skip initial size

            # --- SIGINT handler: forward Ctrl+C to remote (SHLL-03) ---
            def _sigint_handler(signum, frame):
                try:
                    ws.send(bytes([_FRAME_STDIN, 0x03]))
                except Exception:
                    pass  # WebSocket closed: allow exit

            # --- SIGWINCH handler: forward terminal resize ---
            try:
                _initial_size = os.get_terminal_size()
            except OSError:
                _initial_size = None
            _last_size = [_initial_size]

            def _sigwinch_handler(signum, frame):
                try:
                    new_size = os.get_terminal_size()
                except OSError:
                    # No terminal available (e.g., after session ends or in CI)
                    # Fall back to last known size if we haven't sent it yet
                    new_size = _last_size[0]
                if new_size is not None:
                    try:
                        ws.send(bytes([_FRAME_RESIZE]) + struct.pack(">HH", new_size.lines, new_size.columns))
                        _last_size[0] = new_size
                    except Exception:
                        pass

            original_sigint = signal.signal(signal.SIGINT, _sigint_handler)
            original_sigwinch = signal.signal(signal.SIGWINCH, _sigwinch_handler)

            fd_stdin = sys.stdin.fileno()
            orig_flags = fcntl.fcntl(fd_stdin, fcntl.F_GETFL)
            fcntl.fcntl(fd_stdin, fcntl.F_SETFL, orig_flags | os.O_NONBLOCK)

            try:
                self._run_io_loop(ws)
            finally:
                fcntl.fcntl(fd_stdin, fcntl.F_SETFL, orig_flags)
                signal.signal(signal.SIGINT, original_sigint)
                signal.signal(signal.SIGWINCH, original_sigwinch)
                self._ws = None

    def _run_io_loop(self, ws) -> None:
        """select()-based I/O multiplexer: stdin->WebSocket and WebSocket->stdout/stderr.

        Runs until frame 102 (exit result) is received or the connection closes.
        Uses select() with 1-second timeout to interleave stdin reads with WebSocket polls.
        """
        fd_stdin = sys.stdin.fileno()

        while True:
            # Multiplex: wait up to 1s for stdin activity
            readable, _, _ = select.select([fd_stdin], [], [], 1.0)

            # stdin -> frame 104 (stdin to remote)
            if fd_stdin in readable:
                try:
                    chunk = os.read(fd_stdin, 4096)
                    if chunk:
                        ws.send(bytes([_FRAME_STDIN]) + chunk)
                except (OSError, BlockingIOError):
                    pass

            # WebSocket -> stdout/stderr
            try:
                raw = ws.recv(timeout=0.05)
                if isinstance(raw, bytes) and len(raw) >= 1:
                    code = raw[0]
                    payload = raw[1:]
                    if code == _FRAME_STDOUT:
                        sys.stdout.buffer.write(payload)
                        sys.stdout.buffer.flush()
                    elif code == _FRAME_STDERR:
                        sys.stderr.buffer.write(payload)
                        sys.stderr.buffer.flush()
                    elif code == _FRAME_RESULT:
                        return  # Session complete (exit code received)
                    elif code == _FRAME_FAILURE:
                        raise RuntimeError(
                            f"Provider error: {payload.decode('utf-8', errors='replace')}"
                        )
            except (ConnectionClosedOK, ConnectionClosedError):
                return  # Normal or error close
            except TimeoutError:
                pass  # recv timeout: loop continues polling stdin

    def validate(self) -> bool:
        """Return True if deployment has an active lease with a provider hostUri."""
        leases = self._config.deployment.get("leases", [])
        if not leases or not isinstance(leases, list):
            return False
        lease = leases[0]
        if not isinstance(lease, dict):
            return False
        provider = lease.get("provider", {})
        if not isinstance(provider, dict):
            return False
        return bool(provider.get("hostUri") or provider.get("host_uri"))
