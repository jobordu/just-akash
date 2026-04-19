"""Unit tests for LeaseShellTransport.exec() and supporting methods."""

import io
import json
import pytest
from unittest.mock import MagicMock, patch, call

from websockets.exceptions import ConnectionClosedOK

from just_akash.transport.lease_shell import LeaseShellTransport
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

    def close(self):
        pass


# --- Fixtures ---

DEPLOYMENT_FIXTURE = {
    "leases": [{
        "provider": {"hostUri": "https://provider.us-east.akash.pub:8443"},
        "status": {"services": {"web": {"ready_replicas": 1, "total": 1}}},
    }]
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

        with patch.object(
            transport, "_get_api_client"
        ) as mock_get_api:
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

class TestProviderURLExtraction:
    """Test _extract_provider_url() and related methods."""

    def test_extract_provider_url_happy_path(self):
        """Test _extract_provider_url() returns correct (ws_base, service)."""
        config = TransportConfig(
            dseq="999",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
            service_name="web",
        )
        transport = LeaseShellTransport(config)

        ws_base, service = transport._extract_provider_url()

        assert ws_base == "wss://provider.us-east.akash.pub:8443"
        assert service == "web"

    def test_extract_provider_url_https_to_wss_conversion(self):
        """Test HTTPS → WSS protocol conversion."""
        config = TransportConfig(
            dseq="1",
            api_key="k",
            deployment={
                "leases": [{
                    "provider": {"hostUri": "https://example.com:9000"},
                    "status": {"services": {"api": {}}},
                }]
            },
        )
        transport = LeaseShellTransport(config)

        ws_base, service = transport._extract_provider_url()

        assert ws_base == "wss://example.com:9000"

    def test_extract_provider_url_http_to_ws_conversion(self):
        """Test HTTP → WS protocol conversion."""
        config = TransportConfig(
            dseq="2",
            api_key="k",
            deployment={
                "leases": [{
                    "provider": {"hostUri": "http://localhost:8080"},
                    "status": {"services": {"service1": {}}},
                }]
            },
        )
        transport = LeaseShellTransport(config)

        ws_base, service = transport._extract_provider_url()

        assert ws_base == "ws://localhost:8080"

    def test_extract_provider_url_no_leases(self):
        """Test _extract_provider_url() raises RuntimeError when no leases."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={"leases": []},
        )
        transport = LeaseShellTransport(config)

        with pytest.raises(RuntimeError, match="No leases found"):
            transport._extract_provider_url()

    def test_extract_provider_url_missing_hostUri(self):
        """Test _extract_provider_url() raises RuntimeError when hostUri missing."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [{
                    "provider": {},  # No hostUri
                    "status": {"services": {"web": {}}},
                }]
            },
        )
        transport = LeaseShellTransport(config)

        with pytest.raises(RuntimeError, match="Provider hostUri not found"):
            transport._extract_provider_url()

    def test_extract_provider_url_host_uri_snake_case_fallback(self):
        """Test _extract_provider_url() falls back to host_uri (snake_case)."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [{
                    "provider": {"host_uri": "https://snake-case.example.com"},  # snake_case
                    "status": {"services": {"app": {}}},
                }]
            },
        )
        transport = LeaseShellTransport(config)

        ws_base, service = transport._extract_provider_url()

        assert ws_base == "wss://snake-case.example.com"

    def test_extract_provider_url_missing_service_name(self):
        """Test _extract_provider_url() raises RuntimeError when service cannot be determined."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [{
                    "provider": {"hostUri": "https://provider.com"},
                    "status": {"services": {}},  # Empty services
                }]
            },
            service_name=None,  # And no explicit service_name
        )
        transport = LeaseShellTransport(config)

        with pytest.raises(RuntimeError, match="Cannot determine service name"):
            transport._extract_provider_url()


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
        """Test exec() captures stdout and returns exit code."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)

        # Prepare first
        transport.prepare()

        # Mock JWT fetch
        with patch.object(transport, "_fetch_jwt", return_value="test-jwt"):
            # Mock WebSocket with stdout then exit code
            frames = [
                bytes([100]) + b"output\n",
                bytes([102]) + (0).to_bytes(4, "little"),
            ]

            with patch("just_akash.transport.lease_shell.connect") as mock_connect:
                mock_connect.return_value = FakeWebSocket(frames)

                exit_code = transport.exec("echo hello")

        assert exit_code == 0
        mock_connect.assert_called_once()
        call_args = mock_connect.call_args
        # Check URL contains command
        assert "cmd=" in call_args[0][0]
        assert "echo+hello" in call_args[0][0]

    def test_exec_captures_stderr(self):
        """Test exec() captures both stdout and stderr."""
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
        """Test exec() returns non-zero exit code from remote command."""
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

    def test_exec_jwt_bearer_token_in_headers(self):
        """Test exec() includes JWT in Authorization header."""
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
                mock_connect.return_value = FakeWebSocket(frames)

                transport.exec("test")

        call_args = mock_connect.call_args
        additional_headers = call_args.kwargs.get("additional_headers", {})
        assert additional_headers.get("Authorization") == "Bearer token-xyz"

    def test_exec_compression_disabled(self):
        """Test exec() disables compression for provider compatibility."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        transport.prepare()

        with patch.object(transport, "_fetch_jwt", return_value="jwt"):
            with patch("just_akash.transport.lease_shell.connect") as mock_connect:
                mock_connect.return_value = FakeWebSocket([
                    bytes([102]) + (0).to_bytes(4, "little"),
                ])

                transport.exec("test")

        call_args = mock_connect.call_args
        assert call_args.kwargs.get("compression") is None

    def test_exec_auto_prepare(self):
        """Test exec() calls prepare() if ws_url not yet set."""
        config = TransportConfig(
            dseq="999",
            api_key="key",
            deployment=DEPLOYMENT_FIXTURE,
        )
        transport = LeaseShellTransport(config)
        # NOT calling prepare() before exec()

        with patch.object(transport, "_fetch_jwt", return_value="jwt"):
            with patch.object(transport, "prepare") as mock_prepare:
                with patch("just_akash.transport.lease_shell.connect") as mock_connect:
                    mock_connect.return_value = FakeWebSocket([
                        bytes([102]) + (0).to_bytes(4, "little"),
                    ])

                    # First prepare() will be auto-called; mock it to avoid real extraction
                    mock_prepare.side_effect = lambda: setattr(transport, "_ws_url", "wss://x") or setattr(transport, "_service", "s")

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
                "leases": [{
                    "provider": {"host_uri": "https://example.com"},
                }]
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
                "leases": [{
                    "provider": {},  # No hostUri
                }]
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
                "leases": [{
                    "provider": "not-a-dict",
                }]
            },
        )
        transport = LeaseShellTransport(config)

        assert transport.validate() is False


# --- NotImplemented Methods ---

class TestNotImplementedMethods:
    """Test that inject() and connect() raise NotImplementedError."""

    def test_inject_not_implemented(self):
        """Test inject() raises NotImplementedError."""
        config = TransportConfig(dseq="123", api_key="key")
        transport = LeaseShellTransport(config)

        with pytest.raises(NotImplementedError, match="inject.*Phase 8"):
            transport.inject("/tmp/file", "content")

    def test_connect_not_implemented(self):
        """Test connect() raises NotImplementedError."""
        config = TransportConfig(dseq="123", api_key="key")
        transport = LeaseShellTransport(config)

        with pytest.raises(NotImplementedError, match="connect.*Phase 9"):
            transport.connect()
