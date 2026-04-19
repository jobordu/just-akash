"""Unit tests for just_akash.transport package."""

import pytest
from unittest.mock import MagicMock, patch

from just_akash.transport import (
    Transport,
    TransportConfig,
    SSHTransport,
    LeaseShellTransport,
    make_transport,
)


# --- Transport ABC ---

class TestTransportABC:
    def test_transport_cannot_be_instantiated_directly(self):
        """Transport is abstract — direct instantiation must raise TypeError."""
        with pytest.raises(TypeError):
            Transport()  # type: ignore[abstract]

    def test_transport_config_dataclass(self):
        config = TransportConfig(dseq="123456", api_key="key-abc")
        assert config.dseq == "123456"
        assert config.api_key == "key-abc"
        assert config.console_url == "https://console-api.akash.network"
        assert config.service_name is None
        assert config.ssh_key_path is None


# --- SSHTransport ---

class TestSSHTransport:
    def _make_deployment_with_ssh(self):
        """Minimal deployment dict that _extract_ssh_info can parse."""
        return {
            "leases": [
                {
                    "status": {
                        "forwarded_ports": {
                            "app": [
                                {"port": 22, "host": "provider.akash.network", "externalPort": 32022}
                            ]
                        }
                    }
                }
            ]
        }

    def test_validate_returns_true_when_ssh_port_present(self):
        dep = self._make_deployment_with_ssh()
        config = TransportConfig(dseq="123", api_key="key", deployment=dep)
        t = SSHTransport(config)
        assert t.validate() is True

    def test_validate_returns_false_when_no_ssh(self):
        config = TransportConfig(dseq="123", api_key="key", deployment={})
        t = SSHTransport(config)
        assert t.validate() is False

    def test_prepare_raises_when_no_ssh_port(self):
        config = TransportConfig(dseq="123", api_key="key", deployment={})
        t = SSHTransport(config)
        with pytest.raises(RuntimeError):
            t.prepare()

    def test_prepare_raises_when_no_ssh_key(self):
        dep = self._make_deployment_with_ssh()
        config = TransportConfig(dseq="123", api_key="key", deployment=dep)
        t = SSHTransport(config)
        with patch("just_akash.transport.ssh._find_ssh_key", return_value=None):
            with pytest.raises(RuntimeError, match="No SSH key"):
                t.prepare()

    def test_exec_runs_command_and_returns_exit_code(self):
        dep = self._make_deployment_with_ssh()
        config = TransportConfig(dseq="123", api_key="key", deployment=dep)
        t = SSHTransport(config)
        mock_ssh_info = {"host": "provider.akash.network", "port": 32022}
        t._ssh_info = mock_ssh_info
        t._key_path = "/home/user/.ssh/id_ed25519"

        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("just_akash.transport.ssh._build_ssh_cmd", return_value=["ssh", "-p", "32022"]):
            with patch("just_akash.transport.ssh.subprocess.run", return_value=mock_result):
                rc = t.exec("echo hello")
        assert rc == 0

    def test_exec_propagates_nonzero_exit_code(self):
        config = TransportConfig(dseq="123", api_key="key")
        t = SSHTransport(config)
        t._ssh_info = {"host": "h", "port": 22}
        t._key_path = "/key"
        mock_result = MagicMock()
        mock_result.returncode = 42

        with patch("just_akash.transport.ssh._build_ssh_cmd", return_value=["ssh"]):
            with patch("just_akash.transport.ssh.subprocess.run", return_value=mock_result):
                rc = t.exec("exit 42")
        assert rc == 42


# --- LeaseShellTransport (Phase 7+) ---

class TestLeaseShellTransportStub:
    def _stub_no_deployment(self):
        """Lease shell transport without deployment data."""
        config = TransportConfig(dseq="123", api_key="key")
        return LeaseShellTransport(config)

    def _stub_with_deployment(self):
        """Lease shell transport with minimal valid deployment data."""
        config = TransportConfig(
            dseq="123",
            api_key="key",
            deployment={
                "leases": [{
                    "provider": {"hostUri": "https://provider.example.com"},
                    "status": {"services": {"web": {}}},
                }]
            },
        )
        return LeaseShellTransport(config)

    def test_prepare_raises_when_no_deployment_data(self):
        """Phase 7: prepare() needs deployment data to work."""
        with pytest.raises(RuntimeError, match="No leases found"):
            self._stub_no_deployment().prepare()

    def test_prepare_succeeds_with_deployment(self):
        """Phase 7: prepare() works with valid deployment data."""
        t = self._stub_with_deployment()
        t.prepare()
        assert t._ws_url is not None
        assert t._service is not None

    def test_exec_raises_when_no_deployment(self):
        """Phase 7: exec() needs deployment data."""
        with pytest.raises(RuntimeError, match="No leases found"):
            self._stub_no_deployment().exec("echo hi")

    def test_lease_shell_inject_not_a_stub(self):
        """Phase 8: inject() is implemented (no longer NotImplementedError)."""
        t = self._stub_with_deployment()
        t._ws_url = "wss://p:8443/lease/1/1/1/shell"
        t._service = "web"
        with patch.object(t, "exec", side_effect=[0, 0, 0]):
            # Should NOT raise NotImplementedError
            t.inject("/tmp/x", "content")

    def test_connect_raises_not_implemented(self):
        """Phase 9+: connect() not yet implemented."""
        with pytest.raises(NotImplementedError):
            self._stub_with_deployment().connect()

    def test_validate_returns_false_without_deployment(self):
        """validate() returns False when no hostUri."""
        assert self._stub_no_deployment().validate() is False

    def test_validate_returns_true_with_deployment(self):
        """validate() returns True when hostUri present."""
        assert self._stub_with_deployment().validate() is True


# --- make_transport factory ---

class TestMakeTransport:
    def test_makes_ssh_transport(self):
        t = make_transport("ssh", dseq="123", api_key="key")
        assert isinstance(t, SSHTransport)

    def test_makes_lease_shell_transport(self):
        t = make_transport("lease-shell", dseq="123", api_key="key")
        assert isinstance(t, LeaseShellTransport)

    def test_raises_for_unknown_transport(self):
        with pytest.raises(ValueError, match="Unknown transport"):
            make_transport("ftp", dseq="123", api_key="key")
