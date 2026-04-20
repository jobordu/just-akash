"""Unit tests for LeaseShellTransport.inject() — Phase 8."""

import base64
import shlex
from unittest.mock import patch

import pytest

from just_akash.transport import LeaseShellTransport, TransportConfig


def _make_transport() -> LeaseShellTransport:
    """Helper: LeaseShellTransport pre-configured with a fake deployment."""
    config = TransportConfig(
        dseq="123",
        api_key="test-key",
        deployment={
            "leases": [
                {
                    "provider": {"hostUri": "https://provider.example.com:8443"},
                    "status": {"services": {"web": {"ready_replicas": 1, "total": 1}}},
                }
            ]
        },
    )
    t = LeaseShellTransport(config)
    t._provider_host_uri = "https://provider.example.com:8443"
    t._service = "web"
    return t


class TestLeaseShellTransportInject:
    def test_inject_creates_parent_directory(self):
        """inject() step 1: calls exec() with mkdir -p $(dirname ...)."""
        t = _make_transport()
        with patch.object(t, "exec", side_effect=[0, 0, 0]) as mock_exec:
            t.inject("/tmp/secrets.env", "KEY=value")

        mkdir_call = mock_exec.call_args_list[0][0][0]
        assert "mkdir -p" in mkdir_call
        assert "$(dirname" in mkdir_call
        # remote_path must be shell-quoted in the mkdir command
        assert shlex.quote("/tmp/secrets.env") in mkdir_call

    def test_inject_writes_base64_encoded_content(self):
        """inject() step 2: writes content via echo | base64 -d > path."""
        t = _make_transport()
        content = "SECRET=abc123"
        expected_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")

        with patch.object(t, "exec", side_effect=[0, 0, 0]) as mock_exec:
            t.inject("/tmp/secrets.env", content)

        write_call = mock_exec.call_args_list[1][0][0]
        assert "base64 -d" in write_call
        assert expected_b64 in write_call
        assert shlex.quote("/tmp/secrets.env") in write_call

    def test_inject_sets_file_permissions(self):
        """inject() step 3: calls exec() with chmod 600 <path>."""
        t = _make_transport()
        with patch.object(t, "exec", side_effect=[0, 0, 0]) as mock_exec:
            t.inject("/tmp/secrets.env", "KEY=value")

        chmod_call = mock_exec.call_args_list[2][0][0]
        assert "chmod 600" in chmod_call
        assert shlex.quote("/tmp/secrets.env") in chmod_call

    def test_inject_calls_exec_three_times(self):
        """inject() makes exactly three exec() calls: mkdir, write, chmod."""
        t = _make_transport()
        with patch.object(t, "exec", side_effect=[0, 0, 0]) as mock_exec:
            t.inject("/tmp/secrets.env", "KEY=value")

        assert mock_exec.call_count == 3

    def test_inject_raises_on_mkdir_failure(self):
        """inject() raises RuntimeError if mkdir exec() returns non-zero."""
        t = _make_transport()
        with (
            patch.object(t, "exec", return_value=1),
            pytest.raises(RuntimeError, match="Failed to create directory"),
        ):
            t.inject("/tmp/secrets.env", "KEY=value")

    def test_inject_raises_on_write_failure(self):
        """inject() raises RuntimeError if write exec() returns non-zero."""
        t = _make_transport()
        with (
            patch.object(t, "exec", side_effect=[0, 1, 0]),
            pytest.raises(RuntimeError, match="Failed to write"),
        ):
            t.inject("/tmp/secrets.env", "KEY=value")

    def test_inject_raises_on_chmod_failure(self):
        """inject() raises RuntimeError if chmod exec() returns non-zero."""
        t = _make_transport()
        with (
            patch.object(t, "exec", side_effect=[0, 0, 1]),
            pytest.raises(RuntimeError, match="Failed to set permissions"),
        ):
            t.inject("/tmp/secrets.env", "KEY=value")

    def test_inject_escapes_path_with_shell_metacharacters(self):
        """inject() wraps commands in sh -c for proper shell execution."""
        t = _make_transport()
        dangerous_path = "/tmp/test'; rm -rf /"
        with patch.object(t, "exec", side_effect=[0, 0, 0]) as mock_exec:
            t.inject(dangerous_path, "content")

        for call in mock_exec.call_args_list:
            cmd = call[0][0]
            assert cmd.startswith("sh -c ")

    def test_inject_handles_multiline_content(self):
        """inject() base64-encodes multiline content without issues."""
        t = _make_transport()
        content = "LINE1=val1\nLINE2=val2\n"
        expected_b64 = base64.b64encode(content.encode("utf-8")).decode("ascii")

        with patch.object(t, "exec", side_effect=[0, 0, 0]) as mock_exec:
            t.inject("/tmp/multiline.env", content)

        write_call = mock_exec.call_args_list[1][0][0]
        assert expected_b64 in write_call

    def test_inject_secret_value_not_in_exec_command_plaintext(self):
        """INJS-02: the raw secret value never appears as plaintext in exec() commands."""
        t = _make_transport()
        secret_value = "SUPER_SECRET_PASSWORD_12345"

        with patch.object(t, "exec", side_effect=[0, 0, 0]) as mock_exec:
            t.inject("/tmp/secret.env", f"PASSWORD={secret_value}")

        # The plain text secret must NOT appear in any exec() command string
        for call in mock_exec.call_args_list:
            cmd = call[0][0]
            assert secret_value not in cmd, f"Secret leaked in command: {cmd!r}"

    def test_inject_calls_prepare_if_not_configured(self):
        """inject() calls prepare() automatically if _ws_url is None."""
        t = _make_transport()
        t._provider_host_uri = None
        t._service = None

        with (
            patch.object(t, "prepare") as mock_prepare,
            patch.object(t, "exec", side_effect=[0, 0, 0]),
        ):
            t.inject("/tmp/test.env", "KEY=val")

        mock_prepare.assert_called_once()

    def test_inject_with_empty_content_produces_valid_write_command(self):
        """inject() with empty string content must produce a valid base64-d write command."""
        t = _make_transport()
        with patch.object(t, "exec", side_effect=[0, 0, 0]) as mock_exec:
            t.inject("/tmp/empty.env", "")

        write_call = mock_exec.call_args_list[1][0][0]
        expected_b64 = base64.b64encode(b"").decode("ascii")
        assert "base64 -d" in write_call
        assert shlex.quote(expected_b64) in write_call
