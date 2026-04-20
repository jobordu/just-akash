"""Unit tests for LeaseShellTransport.exec() and supporting methods."""

import io
import json
import pytest
from unittest.mock import MagicMock, patch, call

from websockets.exceptions import ConnectionClosedOK, ConnectionClosedError
from websockets.frames import Close

from just_akash.transport.lease_shell import (
    LeaseShellTransport,
    _is_auth_expiry,
    _is_auth_expiry_message,
)
from just_akash.transport.base import TransportConfig


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
            raise ConnectionClosedOK(None, None)

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


# --- Fixtures ---

DEPLOYMENT_FIXTURE = {
    "leases": [
        {
            "provider": {"hostUri": "https://provider.us-east.akash.pub:8443"},
            "status": {"services": {"web": {"ready_replicas": 1, "total": 1}}},
        }
    ]
}


# --- JWT Fetch Tests ---


class TestJWTFetch:
    """Test _fetch_jwt() and AkashConsoleAPI.create_jwt() integration."""

    def test_fetch_jwt_happy_path(self):
        """Test _fetch_jwt() calls create_jwt and returns token string."""
        config = TransportConfig(
            dseq="123456",
            api_key="test-key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)

        with patch.object(transport, "_get_api_client") as mock_get_api:
            mock_api = MagicMock()
            mock_api.create_jwt.return_value = "jwt-token-abc123"
            mock_get_api.return_value = mock_api

            result = transport._fetch_jwt(ttl=7200)

            assert result == "jwt-token-abc123"
            mock_api.create_jwt.assert_called_once_with("123456", ttl=7200)

    def test_fetch_jwt_with_default_ttl(self):
        """Test _fetch_jwt() uses default TTL of 3600."""
        config = TransportConfig(
            dseq="789",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)

        with patch.object(transport, "_get_api_client") as mock_get_api:
            mock_api = MagicMock()
            mock_api.create_jwt.return_value = "token"
            mock_get_api.return_value = mock_api

            transport._fetch_jwt()

            mock_api.create_jwt.assert_called_once_with("789", ttl=3600)

    def test_fetch_jwt_error_propagates(self):
        """Test _fetch_jwt() propagates RuntimeError from create_jwt."""
        config = TransportConfig(
            dseq="bad",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)

        with patch.object(transport, "_get_api_client") as mock_get_api:
            mock_api = MagicMock()
            mock_api.create_jwt.side_effect = RuntimeError("API error: 403 Forbidden")
            mock_get_api.return_value = mock_api

            with pytest.raises(RuntimeError, match="API error: 403 Forbidden"):
                transport._fetch_jwt()


# --- Provider URL Extraction Tests ---


class TestProviderInfoExtraction:
    """Test _extract_provider_info() and related methods."""

    def test_extract_provider_info_happy_path(self):
        config = TransportConfig(
            dseq="999",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
            service_name="web",
        )
        transport = LeaseShellTransport(config)

        host_uri, service = transport._extract_provider_info()

        assert host_uri == "https://provider.us-east.akash.pub:8443"
        assert service == "web"

    def test_extract_provider_info_https_preserved(self):
        config = TransportConfig(
            dseq="1",
            api_key="k",
            deployment={
                "leases": [
                    {
                        "provider": {"hostUri": "https://example.com:9000"},
                        "status": {"services": {"api": {}}},
                    }
                ]
            },
        )
        transport = LeaseShellTransport(config)

        host_uri, service = transport._extract_provider_info()

        assert host_uri == "https://example.com:9000"

    def test_extract_provider_info_http_preserved(self):
        config = TransportConfig(
            dseq="2",
            api_key="k",
            deployment={
                "leases": [
                    {
                        "provider": {"hostUri": "http://localhost:8080"},
                        "status": {"services": {"service1": {}}},
                    }
                ]
            },
        )
        transport = LeaseShellTransport(config)

        host_uri, service = transport._extract_provider_info()

        assert host_uri == "http://localhost:8080"

    def test_extract_provider_info_no_leases(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={"leases": []},
        )
        transport = LeaseShellTransport(config)

        with pytest.raises(RuntimeError, match="No leases found"):
            transport._extract_provider_info()

    def test_extract_provider_info_missing_hostUri(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [
                    {
                        "provider": {},
                        "status": {"services": {"web": {}}},
                    }
                ]
            },
        )
        transport = LeaseShellTransport(config)

        with pytest.raises(RuntimeError, match="Provider hostUri not found"):
            transport._extract_provider_info()

    def test_extract_provider_info_host_uri_snake_case_fallback(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [
                    {
                        "provider": {"host_uri": "https://snake-case.example.com"},
                        "status": {"services": {"app": {}}},
                    }
                ]
            },
        )
        transport = LeaseShellTransport(config)

        host_uri, service = transport._extract_provider_info()

        assert host_uri == "https://snake-case.example.com"

    def test_extract_provider_info_missing_service_name(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [
                    {
                        "provider": {"hostUri": "https://provider.com"},
                        "status": {"services": {}},
                    }
                ]
            },
            service_name=None,
        )
        transport = LeaseShellTransport(config)

        with pytest.raises(RuntimeError, match="Cannot determine service name"):
            transport._extract_provider_info()


# --- Frame Dispatch Tests ---


class TestFrameDispatch:
    """Test _dispatch_frame() handles all frame codes correctly."""

    def test_dispatch_frame_code_100_stdout(self):
        """Test code 100 writes to sys.stdout.buffer."""
        buf = io.BytesIO()
        with patch("sys.stdout") as mock_stdout:
            mock_stdout.buffer = buf
            result = LeaseShellTransport._dispatch_frame(bytes([100]) + b"hello world")

        assert result is None
        assert buf.getvalue() == b"hello world"

    def test_dispatch_frame_code_101_stderr(self):
        """Test code 101 writes to sys.stderr.buffer."""
        buf = io.BytesIO()
        with patch("sys.stderr") as mock_stderr:
            mock_stderr.buffer = buf
            result = LeaseShellTransport._dispatch_frame(bytes([101]) + b"error message")

        assert result is None
        assert buf.getvalue() == b"error message"

    def test_dispatch_frame_code_102_int32_le(self):
        """Test code 102 with 4-byte LE int32 exit code."""
        # Exit code 42 in little-endian
        frame = bytes([102]) + (42).to_bytes(4, "little")
        result = LeaseShellTransport._dispatch_frame(frame)

        assert result == 42

    def test_dispatch_frame_code_102_json_fallback(self):
        """Test code 102 falls back to JSON parsing when fewer than 4 bytes available."""
        json_payload = json.dumps({"exit_code": 137}).encode("utf-8")
        # Use only 2 bytes of the JSON so int32 parse skips and falls back to JSON
        frame = bytes([102]) + json_payload[:2]
        # Will fail both int32 and JSON parse, so defaults to 0
        result = LeaseShellTransport._dispatch_frame(frame)
        assert result == 0

    def test_dispatch_frame_code_102_zero_default(self):
        """Test code 102 defaults to 0 if both int32 and JSON parsing fail."""
        # Use exactly 3 bytes so int32 skip happens and JSON parse fails
        frame = bytes([102]) + b"bad"
        result = LeaseShellTransport._dispatch_frame(frame)

        assert result == 0

    def test_dispatch_frame_code_102_json_valid_with_less_than_4_bytes(self):
        """Test code 102 with JSON payload when less than 4 bytes available."""
        # Payload with < 4 bytes will skip int32 and try JSON
        json_payload = b'{"exit_code":99}'
        frame = bytes([102]) + json_payload[:2]  # Only 2 bytes, not valid JSON
        result = LeaseShellTransport._dispatch_frame(frame)
        # Should default to 0 since JSON parse will fail
        assert result == 0

    def test_dispatch_frame_code_103_failure(self):
        """Test code 103 raises RuntimeError."""
        frame = bytes([103]) + b"provider error: out of memory"
        with pytest.raises(RuntimeError, match="Provider error: provider error"):
            LeaseShellTransport._dispatch_frame(frame)

    def test_dispatch_frame_code_103_utf8_decode_error(self):
        """Test code 103 handles invalid UTF-8."""
        frame = bytes([103]) + b"\xff\xfe invalid utf8"
        with pytest.raises(RuntimeError, match="Provider error"):
            LeaseShellTransport._dispatch_frame(frame)

    def test_dispatch_frame_unknown_code(self):
        """Test unknown frame code returns None."""
        frame = bytes([255]) + b"unknown"
        result = LeaseShellTransport._dispatch_frame(frame)

        assert result is None

    def test_dispatch_frame_empty_bytes(self):
        """Test empty bytes returns None."""
        result = LeaseShellTransport._dispatch_frame(b"")

        assert result is None

    def test_dispatch_frame_non_bytes_input(self):
        """Test non-bytes input returns None."""
        result = LeaseShellTransport._dispatch_frame(None)  # type: ignore

        assert result is None


# --- exec() Happy Path Tests ---


class TestExecHappyPath:
    """Test exec() end-to-end with mocked WebSocket."""

    def test_exec_happy_path_stdout_only(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="test-jwt"):
            frames = [
                bytes([100]) + b"output\n",
                bytes([102]) + (0).to_bytes(4, "little"),
            ]

            with patch("just_akash.transport.lease_shell.connect") as mock_connect:
                fake_ws = FakeWebSocket(frames)
                mock_connect.return_value = fake_ws

                exit_code = transport.exec("echo hello")

        assert exit_code == 0
        mock_connect.assert_called_once()
        connect_msg = json.loads(fake_ws.sent_messages[0])
        assert "cmd=" in connect_msg["url"]
        assert "echo+hello" in connect_msg["url"]

    def test_exec_captures_stderr(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="jwt"):
            frames = [
                bytes([100]) + b"normal output\n",
                bytes([101]) + b"error output\n",
                bytes([102]) + (0).to_bytes(4, "little"),
            ]

            with patch("just_akash.transport.lease_shell.connect") as mock_connect:
                mock_connect.return_value = FakeWebSocket(frames)

                exit_code = transport.exec("some command")

        assert exit_code == 0

    def test_exec_non_zero_exit_code(self):
        config = TransportConfig(
            dseq="456",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="jwt"):
            frames = [
                bytes([100]) + b"command not found\n",
                bytes([102]) + (127).to_bytes(4, "little"),
            ]

            with patch("just_akash.transport.lease_shell.connect") as mock_connect:
                mock_connect.return_value = FakeWebSocket(frames)

                exit_code = transport.exec("nonexistent_cmd")

        assert exit_code == 127

    def test_exec_jwt_sent_in_connect_message(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="token-xyz"):
            frames = [
                bytes([102]) + (0).to_bytes(4, "little"),
            ]

            with patch("just_akash.transport.lease_shell.connect") as mock_connect:
                fake_ws = FakeWebSocket(frames)
                mock_connect.return_value = fake_ws

                transport.exec("test")

        connect_msg = json.loads(fake_ws.sent_messages[0])
        assert connect_msg["auth"]["type"] == "jwt"
        assert connect_msg["auth"]["token"] == "token-xyz"

    def test_exec_compression_disabled(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="jwt"):
            with patch("just_akash.transport.lease_shell.connect") as mock_connect:
                mock_connect.return_value = FakeWebSocket(
                    [
                        bytes([102]) + (0).to_bytes(4, "little"),
                    ]
                )

                transport.exec("test")

        call_args = mock_connect.call_args
        assert call_args.kwargs.get("compression") is None

    def test_exec_auto_prepare(self):
        config = TransportConfig(
            dseq="999",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)

        with patch.object(transport, "_fetch_jwt", return_value="jwt"):
            with patch.object(transport, "prepare") as mock_prepare:
                with patch("just_akash.transport.lease_shell.connect") as mock_connect:
                    mock_connect.return_value = FakeWebSocket(
                        [
                            bytes([102]) + (0).to_bytes(4, "little"),
                        ]
                    )

                    mock_prepare.side_effect = lambda: (
                        setattr(transport, "_service", "s")
                        or setattr(transport, "_provider_host_uri", "https://x")
                    )

                    transport.exec("cmd")

                mock_prepare.assert_called_once()


# --- validate() Tests ---


class TestValidate:
    """Test validate() method."""

    def test_validate_true_with_hostUri(self):
        """Test validate() returns True when deployment has hostUri."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)

        assert transport.validate() is True

    def test_validate_true_with_host_uri_snake_case(self):
        """Test validate() returns True with host_uri (snake_case)."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [
                    {
                        "provider": {"host_uri": "https://example.com"},
                    }
                ]
            },
        )
        transport = LeaseShellTransport(config)

        assert transport.validate() is True

    def test_validate_false_with_empty_leases(self):
        """Test validate() returns False with empty leases."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={"leases": []},
        )
        transport = LeaseShellTransport(config)

        assert transport.validate() is False

    def test_validate_false_with_missing_hostUri(self):
        """Test validate() returns False when hostUri missing."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [
                    {
                        "provider": {},  # No hostUri
                    }
                ]
            },
        )
        transport = LeaseShellTransport(config)

        assert transport.validate() is False

    def test_validate_false_with_non_dict_provider(self):
        """Test validate() returns False when provider is not a dict."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [
                    {
                        "provider": "not-a-dict",
                    }
                ]
            },
        )
        transport = LeaseShellTransport(config)

        assert transport.validate() is False


# --- NotImplemented Methods ---


class TestNotImplementedMethods:
    """Test that connect() raises NotImplementedError (inject() is implemented in Phase 8)."""

    def test_inject_implemented_phase_8(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [
                    {
                        "provider": {"hostUri": "https://provider.example.com:8443"},
                        "status": {"services": {"web": {}}},
                    }
                ]
            },
        )
        transport = LeaseShellTransport(config)
        transport._provider_host_uri = "https://provider.example.com:8443"
        transport._service = "web"
        from unittest.mock import patch

        with patch.object(transport, "exec", side_effect=[0, 0, 0]):
            transport.inject("/tmp/file", "content")

    def test_connect_does_not_raise_not_implemented(self):
        from unittest.mock import patch as _patch

        config = TransportConfig(dseq="123", api_key="key")
        transport = LeaseShellTransport(config)
        transport._provider_host_uri = "https://provider.example.com"
        transport._service = "web"
        with (
            _patch(
                "just_akash.transport.lease_shell.LeaseShellTransport._run_interactive_session"
            ),
            _patch("termios.tcgetattr", return_value=[]),
            _patch("termios.tcsetattr"),
            _patch("tty.setraw"),
            _patch("sys.stdin") as mock_stdin,
        ):
            mock_stdin.isatty.return_value = True
            mock_stdin.fileno.return_value = 0
            transport.connect()


# --- Token Refresh Tests ---


class TestTokenRefresh:
    """Test token-expiry reconnect logic in exec()."""

    def test_exec_reconnects_on_token_expiry(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="jwt-token") as mock_fetch_jwt:
            with patch("just_akash.transport.lease_shell.connect") as mock_connect:

                class FakeWSAuthExpiry:
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
                        bytes([100]) + b"output\n",
                        bytes([102]) + (0).to_bytes(4, "little"),
                    ]
                )

                mock_connect.side_effect = [FakeWSAuthExpiry(), fake_ws_ok]

                exit_code = transport.exec("test cmd")

        assert exit_code == 0
        assert mock_fetch_jwt.call_count == 2
        assert mock_connect.call_count == 2

    def test_exec_reconnects_on_expired_message(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="jwt") as mock_fetch_jwt:
            with patch("just_akash.transport.lease_shell.connect") as mock_connect:

                class FakeWSExpired:
                    def recv(self, timeout=None):
                        raise make_close_error(1000, "token expired")

                    def send(self, data):
                        pass

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        pass

                fake_ws_ok = FakeWebSocket(
                    [
                        bytes([102]) + (2).to_bytes(4, "little"),
                    ]
                )

                mock_connect.side_effect = [FakeWSExpired(), fake_ws_ok]

                exit_code = transport.exec("test")

        assert exit_code == 2
        assert mock_fetch_jwt.call_count == 2

    def test_exec_raises_after_max_reconnect_attempts(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="jwt") as mock_fetch_jwt:
            with patch("just_akash.transport.lease_shell.connect") as mock_connect:

                class FakeWSAuthExpiry:
                    def recv(self, timeout=None):
                        raise make_close_error(4001)

                    def send(self, data):
                        pass

                    def __enter__(self):
                        return self

                    def __exit__(self, *a):
                        pass

                mock_connect.side_effect = [FakeWSAuthExpiry() for _ in range(10)]

                with pytest.raises(RuntimeError, match="Failed to re-authenticate"):
                    transport.exec("test")

        from just_akash.transport.lease_shell import MAX_RECONNECT_ATTEMPTS

        assert mock_fetch_jwt.call_count == MAX_RECONNECT_ATTEMPTS

    def test_exec_non_auth_close_propagates(self):
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="jwt") as mock_fetch_jwt:
            with patch("just_akash.transport.lease_shell.connect") as mock_connect:

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

        assert mock_fetch_jwt.call_count == 1
        assert mock_connect.call_count == 1

    def test_is_auth_expiry_message(self):
        """Test _is_auth_expiry_message() helper function."""
        # True cases
        assert _is_auth_expiry_message("token expired") is True
        assert _is_auth_expiry_message("unauthorized access") is True
        assert _is_auth_expiry_message("Token Expired") is True
        assert _is_auth_expiry_message("UNAUTHORIZED") is True
        assert _is_auth_expiry_message("contains token in message") is True

        # False cases
        assert _is_auth_expiry_message("connection reset") is False
        assert _is_auth_expiry_message("timeout occurred") is False
        assert _is_auth_expiry_message("") is False

    def test_is_auth_expiry_with_close_code(self):
        """Test _is_auth_expiry() detects close codes 4001 and 4003."""
        # Code 4001
        exc_4001 = make_close_error(4001)
        assert _is_auth_expiry(exc_4001) is True

        # Code 4003
        exc_4003 = make_close_error(4003)
        assert _is_auth_expiry(exc_4003) is True

        # Code 1000 (normal) — should return False
        exc_normal = make_close_error(1000)
        assert _is_auth_expiry(exc_normal) is False

    def test_is_auth_expiry_with_reason_string(self):
        """Test _is_auth_expiry() detects auth keywords in reason."""
        exc = make_close_error(1000, "token expired")
        assert _is_auth_expiry(exc) is True

        exc = make_close_error(1000, "unauthorized")
        assert _is_auth_expiry(exc) is True

        exc = make_close_error(1000, "connection reset")
        assert _is_auth_expiry(exc) is False
