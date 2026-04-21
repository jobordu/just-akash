"""Unit tests for transport error paths: token expiry, reconnect, and frame 103."""

import json
from unittest.mock import patch

import pytest
from websockets.exceptions import ConnectionClosedError, ConnectionClosedOK
from websockets.frames import Close

from just_akash.transport.base import TransportConfig
from just_akash.transport.lease_shell import (
    MAX_RECONNECT_ATTEMPTS,
    LeaseShellTransport,
)

# --- FakeWebSocket helper ---


class FakeWebSocket:
    """Minimal WebSocket mock that serves pre-built frames then closes."""

    def __init__(self, frames):
        self._frames = iter(frames)
        self.sent_messages: list = []

    def recv(self, timeout=None):
        try:
            return next(self._frames)
        except StopIteration:
            raise ConnectionClosedOK(None, None) from None

    def send(self, data):
        self.sent_messages.append(data)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def close(self):
        pass


def make_close_error(code: int, reason: str = "") -> ConnectionClosedError:
    """Build a ConnectionClosedError with a specific close code for testing."""
    close_frame = Close(code=code, reason=reason)
    return ConnectionClosedError(rcvd=close_frame, sent=None)


DEPLOYMENT_FIXTURE = {
    "leases": [
        {
            "provider": {"hostUri": "https://provider.us-east.akash.pub:8443"},
            "status": {"services": {"web": {"ready_replicas": 1, "total": 1}}},
        }
    ]
}


# --- Error path tests ---


def test_exec_reconnects_on_close_4001_fetches_new_jwt():
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with (
        patch.object(transport, "_fetch_jwt", side_effect=["jwt-1", "jwt-2"]),
        patch("just_akash.transport.lease_shell.connect") as mock_connect,
    ):

        class FakeWSExpiry:
            def recv(self, timeout=None):
                raise make_close_error(4001)

            def send(self, data):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        fake_ws_ok = FakeWebSocket(
            [
                bytes([102]) + (0).to_bytes(4, "little"),
            ]
        )
        mock_connect.side_effect = [FakeWSExpiry(), fake_ws_ok]

        exit_code = transport.exec("echo hello")

    assert exit_code == 0
    assert mock_connect.call_count == 2


def test_exec_reconnects_on_close_4003():
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with (
        patch.object(transport, "_fetch_jwt", side_effect=["jwt-1", "jwt-2"]),
        patch("just_akash.transport.lease_shell.connect") as mock_connect,
    ):

        class FakeWSExpiry4003:
            def recv(self, timeout=None):
                raise make_close_error(4003)

            def send(self, data):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        fake_ws_ok = FakeWebSocket(
            [
                bytes([102]) + (0).to_bytes(4, "little"),
            ]
        )
        mock_connect.side_effect = [FakeWSExpiry4003(), fake_ws_ok]

        exit_code = transport.exec("ls")

    assert exit_code == 0
    assert mock_connect.call_count == 2


def test_exec_exhausts_max_reconnect_attempts():
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with (
        patch.object(transport, "_fetch_jwt", return_value="jwt"),
        patch("just_akash.transport.lease_shell.connect") as mock_connect,
    ):

        class FakeWSExpiry:
            def recv(self, timeout=None):
                raise make_close_error(4001)

            def send(self, data):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        mock_connect.side_effect = [FakeWSExpiry() for _ in range(MAX_RECONNECT_ATTEMPTS + 5)]

        with pytest.raises(RuntimeError, match="Failed to re-authenticate"):
            transport.exec("test")


def test_exec_raises_immediately_on_non_auth_close_1006():
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with (
        patch.object(transport, "_fetch_jwt", return_value="jwt"),
        patch("just_akash.transport.lease_shell.connect") as mock_connect,
    ):

        class FakeWSAbnormal:
            def recv(self, timeout=None):
                raise make_close_error(1006)

            def send(self, data):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        mock_connect.return_value = FakeWSAbnormal()

        with pytest.raises(ConnectionClosedError):
            transport.exec("test")

    assert mock_connect.call_count == 1


def test_exec_raises_on_frame_103_provider_error():
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with (
        patch.object(transport, "_fetch_jwt", return_value="jwt"),
        patch("just_akash.transport.lease_shell.connect") as mock_connect,
    ):
        frames = [bytes([103]) + b"out of disk space"]
        mock_connect.return_value = FakeWebSocket(frames)

        with pytest.raises(RuntimeError, match="out of disk space"):
            transport.exec("test")

    assert mock_connect.call_count == 1


def test_exec_reconnects_on_reason_string_expired_code_1000():
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with (
        patch.object(transport, "_fetch_jwt", side_effect=["jwt-1", "jwt-2"]),
        patch("just_akash.transport.lease_shell.connect") as mock_connect,
    ):

        class FakeWSExpiredReason:
            def recv(self, timeout=None):
                raise make_close_error(1000, "session expired")

            def send(self, data):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        fake_ws_ok = FakeWebSocket(
            [
                bytes([102]) + (0).to_bytes(4, "little"),
            ]
        )
        mock_connect.side_effect = [FakeWSExpiredReason(), fake_ws_ok]

        exit_code = transport.exec("test")

    assert exit_code == 0
    assert mock_connect.call_count == 2


def test_exec_reconnects_on_reason_string_unauthorized_code_1000():
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with (
        patch.object(transport, "_fetch_jwt", side_effect=["jwt-1", "jwt-2"]),
        patch("just_akash.transport.lease_shell.connect") as mock_connect,
    ):

        class FakeWSUnauthorized:
            def recv(self, timeout=None):
                raise make_close_error(1000, "unauthorized")

            def send(self, data):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        fake_ws_ok = FakeWebSocket(
            [
                bytes([102]) + (0).to_bytes(4, "little"),
            ]
        )
        mock_connect.side_effect = [FakeWSUnauthorized(), fake_ws_ok]

        exit_code = transport.exec("test")

    assert exit_code == 0
    assert mock_connect.call_count == 2


def test_exec_second_jwt_different_from_first():
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    captured_tokens = []

    with (
        patch.object(transport, "_fetch_jwt", side_effect=["jwt-first", "jwt-second"]),
        patch("just_akash.transport.lease_shell.connect") as mock_connect,
    ):

        class FakeWSExpiry:
            def recv(self, timeout=None):
                raise make_close_error(4001)

            def send(self, data):
                captured_tokens.append(json.loads(data)["auth"]["token"])

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        fake_ws_ok = FakeWebSocket(
            [
                bytes([102]) + (0).to_bytes(4, "little"),
            ]
        )
        mock_connect.side_effect = [FakeWSExpiry(), fake_ws_ok]

        transport.exec("test")

    assert len(captured_tokens) == 1
    assert captured_tokens[0] == "jwt-first"
    second_msg = json.loads(fake_ws_ok.sent_messages[0])
    assert second_msg["auth"]["token"] == "jwt-second"


def test_exec_propagates_non_auth_runtime_error_from_jwt_fetch_on_retry():
    """When _fetch_jwt() raises a non-auth RuntimeError after an auth-expiry reconnect,
    it must propagate immediately — NOT retry and NOT raise 'Failed to re-authenticate'."""
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with (
        patch.object(
            transport,
            "_fetch_jwt",
            side_effect=["jwt-ok", RuntimeError("API error: 500 Internal Server Error")],
        ),
        patch("just_akash.transport.lease_shell.connect") as mock_connect,
    ):

        class FakeWSExpiry:
            def recv(self, timeout=None):
                raise make_close_error(4001)

            def send(self, data):
                pass

            def __enter__(self):
                return self

            def __exit__(self, *a):
                pass

        mock_connect.return_value = FakeWSExpiry()

        with pytest.raises(RuntimeError, match="API error: 500 Internal Server Error"):
            transport.exec("test")

    assert mock_connect.call_count == 1
