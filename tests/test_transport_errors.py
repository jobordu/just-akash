"""Unit tests for transport error paths: token expiry, reconnect, and frame 103."""

import pytest
from unittest.mock import patch

from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
from websockets.frames import Close

from just_akash.transport.lease_shell import (
    LeaseShellTransport,
    _is_auth_expiry,
    _is_auth_expiry_message,
    MAX_RECONNECT_ATTEMPTS,
)
from just_akash.transport.base import TransportConfig


# --- FakeWebSocket helper ---

class FakeWebSocket:
    """Minimal WebSocket mock that serves pre-built frames then closes."""
    def __init__(self, frames):
        self._frames = iter(frames)

    def recv(self, timeout=None):
        try:
            return next(self._frames)
        except StopIteration:
            raise ConnectionClosedOK(None, None)

    def __enter__(self):
        return self

    def __exit__(self, *a):
        pass

    def send(self, data):
        pass

    def close(self):
        pass


def make_close_error(code: int, reason: str = "") -> ConnectionClosedError:
    """Build a ConnectionClosedError with a specific close code for testing."""
    close_frame = Close(code=code, reason=reason)
    return ConnectionClosedError(rcvd=close_frame, sent=None)


DEPLOYMENT_FIXTURE = {
    "leases": [{
        "provider": {"hostUri": "https://provider.us-east.akash.pub:8443"},
        "status": {"services": {"web": {"ready_replicas": 1, "total": 1}}},
    }]
}


# --- Error path tests ---

def test_exec_reconnects_on_close_4001_fetches_new_jwt():
    """Close code 4001 triggers reconnect with a freshly-fetched JWT (not cached)."""
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with patch.object(transport, "_fetch_jwt", side_effect=["jwt-1", "jwt-2"]) as mock_fetch:
        with patch("just_akash.transport.lease_shell.connect") as mock_connect:
            # First connect raises auth expiry close code 4001
            class FakeWSExpiry:
                def recv(self, timeout=None):
                    raise make_close_error(4001)
                def __enter__(self): return self
                def __exit__(self, *a): pass

            # Second connect succeeds with exit code 0
            fake_ws_ok = FakeWebSocket([
                bytes([102]) + (0).to_bytes(4, "little"),
            ])
            mock_connect.side_effect = [FakeWSExpiry(), fake_ws_ok]

            exit_code = transport.exec("echo hello")

    assert exit_code == 0
    assert mock_fetch.call_count == 2
    assert mock_connect.call_count == 2


def test_exec_reconnects_on_close_4003():
    """Close code 4003 triggers a reconnect identically to 4001."""
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with patch.object(transport, "_fetch_jwt", side_effect=["jwt-1", "jwt-2"]) as mock_fetch:
        with patch("just_akash.transport.lease_shell.connect") as mock_connect:
            class FakeWSExpiry4003:
                def recv(self, timeout=None):
                    raise make_close_error(4003)
                def __enter__(self): return self
                def __exit__(self, *a): pass

            fake_ws_ok = FakeWebSocket([
                bytes([102]) + (0).to_bytes(4, "little"),
            ])
            mock_connect.side_effect = [FakeWSExpiry4003(), fake_ws_ok]

            exit_code = transport.exec("ls")

    assert exit_code == 0
    assert mock_fetch.call_count == 2
    assert mock_connect.call_count == 2


def test_exec_exhausts_max_reconnect_attempts():
    """Three consecutive auth-expiry closes exhaust MAX_RECONNECT_ATTEMPTS and raise RuntimeError."""
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with patch.object(transport, "_fetch_jwt", return_value="jwt") as mock_fetch:
        with patch("just_akash.transport.lease_shell.connect") as mock_connect:
            class FakeWSExpiry:
                def recv(self, timeout=None):
                    raise make_close_error(4001)
                def __enter__(self): return self
                def __exit__(self, *a): pass

            mock_connect.side_effect = [FakeWSExpiry() for _ in range(MAX_RECONNECT_ATTEMPTS + 5)]

            with pytest.raises(RuntimeError, match="Failed to re-authenticate"):
                transport.exec("test")

    assert mock_fetch.call_count == MAX_RECONNECT_ATTEMPTS


def test_exec_raises_immediately_on_non_auth_close_1006():
    """Non-auth close code 1006 propagates immediately without retry."""
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with patch.object(transport, "_fetch_jwt", return_value="jwt"):
        with patch("just_akash.transport.lease_shell.connect") as mock_connect:
            class FakeWSAbnormal:
                def recv(self, timeout=None):
                    raise make_close_error(1006)
                def __enter__(self): return self
                def __exit__(self, *a): pass

            mock_connect.return_value = FakeWSAbnormal()

            with pytest.raises(ConnectionClosedError):
                transport.exec("test")

    assert mock_connect.call_count == 1


def test_exec_raises_on_frame_103_provider_error():
    """Frame 103 (provider failure) raises RuntimeError containing the provider message."""
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with patch.object(transport, "_fetch_jwt", return_value="jwt"):
        with patch("just_akash.transport.lease_shell.connect") as mock_connect:
            frames = [bytes([103]) + b"out of disk space"]
            mock_connect.return_value = FakeWebSocket(frames)

            with pytest.raises(RuntimeError, match="out of disk space"):
                transport.exec("test")

    assert mock_connect.call_count == 1


def test_exec_reconnects_on_reason_string_expired_code_1000():
    """Close code 1000 with reason 'session expired' triggers a reconnect."""
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with patch.object(transport, "_fetch_jwt", side_effect=["jwt-1", "jwt-2"]) as mock_fetch:
        with patch("just_akash.transport.lease_shell.connect") as mock_connect:
            class FakeWSExpiredReason:
                def recv(self, timeout=None):
                    raise make_close_error(1000, "session expired")
                def __enter__(self): return self
                def __exit__(self, *a): pass

            fake_ws_ok = FakeWebSocket([
                bytes([102]) + (0).to_bytes(4, "little"),
            ])
            mock_connect.side_effect = [FakeWSExpiredReason(), fake_ws_ok]

            exit_code = transport.exec("test")

    assert exit_code == 0
    assert mock_connect.call_count == 2


def test_exec_reconnects_on_reason_string_unauthorized_code_1000():
    """Close code 1000 with reason 'unauthorized' triggers a reconnect."""
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with patch.object(transport, "_fetch_jwt", side_effect=["jwt-1", "jwt-2"]) as mock_fetch:
        with patch("just_akash.transport.lease_shell.connect") as mock_connect:
            class FakeWSUnauthorized:
                def recv(self, timeout=None):
                    raise make_close_error(1000, "unauthorized")
                def __enter__(self): return self
                def __exit__(self, *a): pass

            fake_ws_ok = FakeWebSocket([
                bytes([102]) + (0).to_bytes(4, "little"),
            ])
            mock_connect.side_effect = [FakeWSUnauthorized(), fake_ws_ok]

            exit_code = transport.exec("test")

    assert exit_code == 0
    assert mock_connect.call_count == 2


def test_exec_second_jwt_different_from_first():
    """The JWT in the Authorization header changes between reconnect attempts."""
    config = TransportConfig(dseq="123", api_key="key", deployment=DEPLOYMENT_FIXTURE)
    transport = LeaseShellTransport(config)
    transport.prepare()

    with patch.object(transport, "_fetch_jwt", side_effect=["jwt-first", "jwt-second"]):
        with patch("just_akash.transport.lease_shell.connect") as mock_connect:
            class FakeWSExpiry:
                def recv(self, timeout=None):
                    raise make_close_error(4001)
                def __enter__(self): return self
                def __exit__(self, *a): pass

            fake_ws_ok = FakeWebSocket([
                bytes([102]) + (0).to_bytes(4, "little"),
            ])
            mock_connect.side_effect = [FakeWSExpiry(), fake_ws_ok]

            transport.exec("test")

    # Verify the Authorization header differed between the two connect() calls
    assert len(mock_connect.call_args_list) == 2
    first_auth = mock_connect.call_args_list[0].kwargs["additional_headers"]["Authorization"]
    second_auth = mock_connect.call_args_list[1].kwargs["additional_headers"]["Authorization"]
    assert first_auth == "Bearer jwt-first"
    assert second_auth == "Bearer jwt-second"
    assert first_auth != second_auth
