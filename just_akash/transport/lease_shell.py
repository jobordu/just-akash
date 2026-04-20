"""
Lease-shell WebSocket transport via Console Provider-Proxy (Phase 7).

Connects to the Akash Console provider-proxy (wss://provider-proxy.akash.network/)
which relays WebSocket frames to the target provider. Uses JWT auth obtained from
the Console API.

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

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.sync.client import connect

from just_akash.api import AkashConsoleAPI

from .base import Transport, TransportConfig

MAX_RECONNECT_ATTEMPTS = 3

_FRAME_STDOUT = 100
_FRAME_STDERR = 101
_FRAME_RESULT = 102
_FRAME_FAILURE = 103
_FRAME_STDIN = 104
_FRAME_RESIZE = 105


def _is_auth_expiry_message(msg: str) -> bool:
    lower = msg.lower()
    return "expired" in lower or "unauthorized" in lower or "token" in lower


def _is_auth_expiry(exc: ConnectionClosedError) -> bool:
    rcvd = getattr(exc, "rcvd", None)
    if rcvd is not None:
        code = getattr(rcvd, "code", None)
        if code in (4001, 4003):
            return True
        reason = getattr(rcvd, "reason", "") or ""
        if _is_auth_expiry_message(reason):
            return True
    return _is_auth_expiry_message(str(exc))


class LeaseShellTransport(Transport):
    """WebSocket-based lease-shell transport via Console Provider-Proxy.

    Connects to provider-proxy which relays to the actual provider.
    """

    def __init__(self, config: TransportConfig) -> None:
        self._config = config
        self._provider_host_uri: str | None = None
        self._service: str | None = None
        self._provider_address: str | None = None
        self._api_client: AkashConsoleAPI | None = None
        self._ws = None

    def _get_api_client(self) -> AkashConsoleAPI:
        if self._api_client is None:
            self._api_client = AkashConsoleAPI(
                api_key=self._config.api_key,
                base_url=self._config.console_url,
            )
        return self._api_client

    def _fetch_jwt(self, ttl: int = 3600) -> str:
        if self._provider_address:
            return self._get_api_client().create_jwt_with_provider(
                self._config.dseq, self._provider_address, ttl=ttl
            )
        return self._get_api_client().create_jwt(self._config.dseq, ttl=ttl)

    def _extract_provider_info(self) -> tuple[str, str]:
        leases = self._config.deployment.get("leases", [])
        if not leases or not isinstance(leases, list):
            raise RuntimeError(
                f"No leases found for deployment {self._config.dseq}. "
                "The deployment may not have an active lease yet."
            )
        lease = leases[0]
        if not isinstance(lease, dict):
            raise RuntimeError("Unexpected lease entry format in deployment data.")

        provider_addr = lease.get("id", {}).get("provider", "")
        if provider_addr:
            self._provider_address = provider_addr

        provider = lease.get("provider", {})
        if not isinstance(provider, dict):
            raise RuntimeError("Unexpected provider format in lease data.")
        host_uri: str | None = provider.get("hostUri") or provider.get("host_uri")
        if not host_uri:
            raise RuntimeError(
                "Provider hostUri not found in deployment lease data. "
                f"Available provider keys: {list(provider.keys())}"
            )
        self._provider_host_uri = host_uri

        service = self._config.service_name or self._infer_service()
        if not service:
            raise RuntimeError(
                "Cannot determine service name. Pass service_name in TransportConfig "
                "or ensure deployment has an active service in lease status."
            )
        self._service = service
        return host_uri, service

    def _infer_service(self) -> str | None:
        leases = self._config.deployment.get("leases", [])
        if not leases:
            return None
        lease = leases[0] if isinstance(leases, list) else {}
        status = lease.get("status", {}) if isinstance(lease, dict) else {}
        services = status.get("services", {}) if isinstance(status, dict) else {}
        if isinstance(services, dict) and services:
            return next(iter(services))
        return None

    def _build_provider_ws_url(
        self, command: str | None = None, tty: bool = False, stdin: bool = False
    ) -> str:
        ws_base = self._provider_host_uri.replace("https://", "wss://").replace("http://", "ws://")
        dseq = self._config.dseq
        params: dict[str, str] = {
            "service": self._service,
            "tty": "true" if tty else "false",
            "stdin": "true" if stdin else "false",
        }
        if command is not None:
            params["cmd"] = command
        qs = urllib.parse.urlencode(params)
        return f"{ws_base}/lease/{dseq}/1/1/shell?{qs}"

    def _build_proxy_connect_msg(
        self, provider_ws_url: str, jwt: str, stdin_data: str | None = None
    ) -> str:
        msg: dict = {
            "type": "websocket",
            "url": provider_ws_url,
            "providerAddress": self._provider_address,
            "auth": {"type": "jwt", "token": jwt},
        }
        if stdin_data is not None:
            msg["data"] = base64.b64encode(stdin_data.encode("utf-8")).decode("ascii")
            msg["isBase64"] = True
        return json.dumps(msg)

    def _get_proxy_ws_url(self) -> str:
        proxy = self._config.provider_proxy_url
        return proxy.replace("https://", "wss://").replace("http://", "ws://")

    @staticmethod
    def _dispatch_frame(frame: bytes) -> int | None:
        if not isinstance(frame, bytes) or len(frame) < 1:
            return None
        code = frame[0]
        payload = frame[1:]
        if code == 100:
            sys.stdout.buffer.write(payload)
            sys.stdout.buffer.flush()
        elif code == 101:
            sys.stderr.buffer.write(payload)
            sys.stderr.buffer.flush()
        elif code == 102:
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
        elif code == 103:
            msg = payload.decode("utf-8", errors="replace")
            raise RuntimeError(f"Provider error: {msg}")
        return None

    def _recv_proxy_message(self, ws, timeout: float = 300) -> bytes | None:
        raw = ws.recv(timeout=timeout)
        if isinstance(raw, bytes):
            return raw
        if isinstance(raw, str):
            try:
                msg = json.loads(raw)
                if msg.get("type") == "error":
                    raise RuntimeError(f"Proxy error: {msg.get('message', msg)}")
                message = msg.get("message")
                if isinstance(message, str):
                    return base64.b64decode(message)
                if isinstance(message, (bytes, bytearray)):
                    return bytes(message)
                if isinstance(msg.get("data"), str):
                    return base64.b64decode(msg["data"])
            except (json.JSONDecodeError, TypeError):
                pass
        return None

    def _exec_with_refresh(self, command: str) -> int:
        attempts = 0
        exit_code = 0

        while attempts < MAX_RECONNECT_ATTEMPTS:
            jwt = self._fetch_jwt()
            provider_ws_url = self._build_provider_ws_url(command=command)
            proxy_url = self._get_proxy_ws_url()
            connect_msg = self._build_proxy_connect_msg(provider_ws_url, jwt)
            ssl_ctx = ssl.create_default_context()

            try:
                with connect(
                    proxy_url,
                    ssl=ssl_ctx,
                    compression=None,
                    open_timeout=30,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    ws.send(connect_msg)
                    while True:
                        try:
                            frame = self._recv_proxy_message(ws, timeout=300)
                        except ConnectionClosedOK:
                            return exit_code
                        except ConnectionClosedError as exc:
                            if _is_auth_expiry(exc):
                                break
                            raise
                        if frame is None:
                            continue
                        result = self._dispatch_frame(frame)
                        if result is not None:
                            return result
            except RuntimeError as exc:
                if _is_auth_expiry_message(str(exc)):
                    pass
                else:
                    raise
            attempts += 1

        raise RuntimeError(
            f"Failed to re-authenticate after {MAX_RECONNECT_ATTEMPTS} attempts. "
            "Check that AKASH_API_KEY is valid and the deployment is active."
        )

    def prepare(self) -> None:
        self._extract_provider_info()

    def exec(self, command: str) -> int:
        if self._service is None:
            self.prepare()
        return self._exec_with_refresh(command)

    def inject(self, remote_path: str, content: str) -> None:
        if self._service is None:
            self.prepare()

        mkdir_cmd = f"mkdir -p $(dirname {shlex.quote(remote_path)})"
        rc = self.exec(mkdir_cmd)
        if rc != 0:
            raise RuntimeError(f"Failed to create directory for {remote_path}: exit {rc}")

        encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
        write_cmd = f"echo {shlex.quote(encoded)} | base64 -d > {shlex.quote(remote_path)}"
        rc = self.exec(write_cmd)
        if rc != 0:
            raise RuntimeError(f"Failed to write {remote_path}: exit {rc}")

        chmod_cmd = f"chmod 600 {shlex.quote(remote_path)}"
        rc = self.exec(chmod_cmd)
        if rc != 0:
            raise RuntimeError(f"Failed to set permissions on {remote_path}: exit {rc}")

    def connect(self) -> None:
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
        if self._service is None:
            self.prepare()

        fd = sys.stdin.fileno()
        original_settings = termios.tcgetattr(fd)

        try:
            tty.setraw(fd)
            self._run_interactive_session()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, original_settings)

    def _run_interactive_session(self) -> None:
        jwt = self._fetch_jwt()
        provider_ws_url = self._build_provider_ws_url(tty=True, stdin=True)
        proxy_url = self._get_proxy_ws_url()
        connect_msg = self._build_proxy_connect_msg(provider_ws_url, jwt)
        ssl_ctx = ssl.create_default_context()

        with connect(
            proxy_url,
            ssl=ssl_ctx,
            compression=None,
            open_timeout=30,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            ws.send(connect_msg)
            self._ws = ws

            try:
                size = os.get_terminal_size()
                resize_frame = bytes([_FRAME_RESIZE]) + struct.pack(
                    ">HH", size.lines, size.columns
                )
                ws.send(
                    json.dumps(
                        {
                            "type": "websocket",
                            "data": base64.b64encode(resize_frame).decode("ascii"),
                            "isBase64": True,
                        }
                    )
                )
            except OSError:
                pass

            def _sigint_handler(signum, frame):
                try:
                    stdin_frame = bytes([_FRAME_STDIN, 0x03])
                    ws.send(
                        json.dumps(
                            {
                                "type": "websocket",
                                "data": base64.b64encode(stdin_frame).decode("ascii"),
                                "isBase64": True,
                            }
                        )
                    )
                except Exception:
                    pass

            try:
                _initial_size = os.get_terminal_size()
            except OSError:
                _initial_size = None
            _last_size = [_initial_size]

            def _sigwinch_handler(signum, frame):
                try:
                    new_size = os.get_terminal_size()
                except OSError:
                    new_size = _last_size[0]
                if new_size is not None:
                    try:
                        resize = bytes([_FRAME_RESIZE]) + struct.pack(
                            ">HH", new_size.lines, new_size.columns
                        )
                        ws.send(
                            json.dumps(
                                {
                                    "type": "websocket",
                                    "data": base64.b64encode(resize).decode("ascii"),
                                    "isBase64": True,
                                }
                            )
                        )
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
        fd_stdin = sys.stdin.fileno()

        while True:
            readable, _, _ = select.select([fd_stdin], [], [], 1.0)

            if fd_stdin in readable:
                try:
                    chunk = os.read(fd_stdin, 4096)
                    if chunk:
                        stdin_frame = bytes([_FRAME_STDIN]) + chunk
                        ws.send(
                            json.dumps(
                                {
                                    "type": "websocket",
                                    "data": base64.b64encode(stdin_frame).decode("ascii"),
                                    "isBase64": True,
                                }
                            )
                        )
                except (OSError, BlockingIOError):
                    pass

            try:
                frame = self._recv_proxy_message(ws, timeout=0.05)
                if frame is not None and len(frame) >= 1:
                    code = frame[0]
                    payload = frame[1:]
                    if code == _FRAME_STDOUT:
                        sys.stdout.buffer.write(payload)
                        sys.stdout.buffer.flush()
                    elif code == _FRAME_STDERR:
                        sys.stderr.buffer.write(payload)
                        sys.stderr.buffer.flush()
                    elif code == _FRAME_RESULT:
                        return
                    elif code == _FRAME_FAILURE:
                        raise RuntimeError(
                            f"Provider error: {payload.decode('utf-8', errors='replace')}"
                        )
            except (ConnectionClosedOK, ConnectionClosedError):
                return
            except TimeoutError:
                pass

    def validate(self) -> bool:
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
