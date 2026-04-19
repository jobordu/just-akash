"""
Lease-shell WebSocket transport (Phase 7).

Implements non-interactive command execution over the Akash provider WebSocket
using a JWT bearer token obtained from the Console API.

Protocol reference: docs/PROTOCOL.md
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.parse
from typing import TYPE_CHECKING

from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.sync.client import connect

from just_akash.api import AkashConsoleAPI

from .base import Transport, TransportConfig


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

        Uses websockets.sync.client (NOT asyncio) — Transport.exec() is synchronous.
        compression=None: disable permessage-deflate (provider compatibility).
        """
        if self._ws_url is None or self._service is None:
            self.prepare()

        jwt = self._fetch_jwt()
        params = urllib.parse.urlencode({
            "cmd": command,
            "service": self._service,
            "tty": "false",
            "stdin": "false",
        })
        url = f"{self._ws_url}?{params}"

        ssl_ctx = self._make_ssl_context()
        headers = {"Authorization": f"Bearer {jwt}"}

        exit_code = 0
        with connect(
            url,
            additional_headers=headers,
            ssl=ssl_ctx,
            compression=None,          # disable deflate for provider compat
            open_timeout=30,
            ping_interval=20,
            ping_timeout=20,
        ) as ws:
            while True:
                try:
                    frame = ws.recv(timeout=300)  # 5-minute max per command
                except (ConnectionClosedOK, ConnectionClosedError):
                    break
                result = self._dispatch_frame(frame)
                if result is not None:
                    exit_code = result
                    break
        return exit_code

    def inject(self, remote_path: str, content: str) -> None:
        raise NotImplementedError(
            "LeaseShellTransport.inject() not yet implemented. "
            "Available in Phase 8. Use --transport ssh for now."
        )

    def connect(self) -> None:
        raise NotImplementedError(
            "LeaseShellTransport.connect() not yet implemented. "
            "Available in Phase 9. Use --transport ssh for now."
        )

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
