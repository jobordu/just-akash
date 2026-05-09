"""Tests for just_akash.deploy — deployment orchestrator."""

from unittest.mock import patch

import pytest

from just_akash.deploy import _fmt_price, _log_bid_table, deploy


class TestFmtPrice:
    def test_normal(self):
        bid = {"price": {"amount": 100, "denom": "uakt"}}
        assert _fmt_price(bid) == "100.0 uakt"

    def test_usd(self):
        bid = {"price": {"amount": 5, "denom": "usd"}}
        assert _fmt_price(bid) == "5.0 usd"


class TestLogBidTable:
    def test_empty_bids(self, capsys):
        _log_bid_table([], "TEST")
        captured = capsys.readouterr()
        assert "(none)" in captured.out

    def test_with_bids(self, capsys):
        bids = [{"id": {"provider": "akash1a"}, "price": {"amount": 10, "denom": "uakt"}}]
        _log_bid_table(bids, "TEST")
        captured = capsys.readouterr()
        assert "1 bid(s)" in captured.out


SDL_YAML = """
version: "2.0"
services:
  web:
    image: python:3.13-slim
    expose:
      - port: 22
        as: 22
        to:
          - global: true
"""

SDL_WITH_SSH_PLACEHOLDER = SDL_YAML.replace(
    "image: python:3.13-slim",
    "image: python:3.13-slim\n    env:\n      - SSH_PUBKEY_B64=PLACEHOLDER_SSH_PUBKEY_B64",
)


def _make_bid(provider, amount, denom="uakt"):
    return {
        "id": {"provider": provider},
        "price": {"amount": amount, "denom": denom},
        "state": "open",
    }


def _time_mock():
    counter = [0.0]

    def advance():
        counter[0] += 1
        return counter[0]

    return advance


class TestDeployMissingApiKey:
    def test_raises_without_api_key(self, tmp_path, monkeypatch):
        monkeypatch.delenv("AKASH_API_KEY", raising=False)
        with pytest.raises(RuntimeError, match="AKASH_API_KEY"):
            deploy(sdl_path=str(tmp_path / "fake.yaml"))


class TestDeploySdlNotFound:
    def test_raises_for_missing_sdl(self, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        with pytest.raises(RuntimeError, match="SDL file not found"):
            deploy(sdl_path="/nonexistent/file.yaml")


class TestDeploySshPubkeyMissing:
    def test_raises_when_ssh_placeholder_and_no_key(self, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("SSH_PUBKEY", raising=False)
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_WITH_SSH_PLACEHOLDER)
        with pytest.raises(RuntimeError, match="SSH_PUBKEY"):
            deploy(sdl_path=str(sdl_file))


class TestDeployNoDseq:
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_raises_when_no_dseq_in_response(self, MockAPI, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"manifest": "abc"}

        with pytest.raises(RuntimeError, match="No DSEQ returned"):
            deploy(sdl_path=str(sdl_file))


class TestDeployNoBids:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_raises_when_no_bids_received(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = []

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        with pytest.raises(RuntimeError, match="No bids received"):
            deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)


class TestDeployOnlyForeignBids:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_raises_when_only_foreign_bids(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.setenv("AKASH_PROVIDERS", "akash1allowed")
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [_make_bid("akash1foreign", 50)]

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        with pytest.raises(RuntimeError, match="NONE from our providers"):
            deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)


class TestDeploySuccess:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_successful_deployment_no_allowlist(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [_make_bid("akash1prov", 100)]
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        result = deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)
        assert result["dseq"] == "12345"
        assert result["provider"] == "akash1prov"
        assert result["price"] == 100.0
        assert result["price_denom"] == "uakt"

    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_successful_deployment_with_allowlist(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.setenv("AKASH_PROVIDERS", "akash1allowed,akash1other")
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [
            _make_bid("akash1allowed", 100),
            _make_bid("akash1other", 80),
        ]
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        result = deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)
        assert result["provider"] == "akash1other"
        assert result["price"] == 80.0


class TestDeployImageOverride:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_image_override(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [_make_bid("akash1prov", 50)]
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        result = deploy(
            sdl_path=str(sdl_file), image="ubuntu:22.04", bid_wait=10, bid_wait_retry=10
        )
        assert result["dseq"] == "12345"
        call_args = client.create_deployment.call_args[0][0]
        assert "ubuntu:22.04" in call_args


class TestDeploySshKeyInjection:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_ssh_key_injected(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.setenv("SSH_PUBKEY", "ssh-ed25519 AAAA test@key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_WITH_SSH_PLACEHOLDER)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [_make_bid("akash1prov", 50)]
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        result = deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)
        assert result["dseq"] == "12345"
        call_args = client.create_deployment.call_args[0][0]
        assert "PLACEHOLDER_SSH_PUBKEY_B64" not in call_args


class TestDeployCreateDeploymentFails:
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_create_deployment_error(self, MockAPI, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.side_effect = RuntimeError("API down")

        with pytest.raises(RuntimeError, match="Failed to create deployment"):
            deploy(sdl_path=str(sdl_file))


class TestDeployLeaseCreationFails:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_lease_creation_error(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [_make_bid("akash1prov", 50)]
        client.create_lease.side_effect = RuntimeError("Lease failed")

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        with pytest.raises(RuntimeError, match="Failed to create lease"):
            deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)


class TestDeployBidApiError:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_api_error_then_success(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        call_count = [0]

        def bids_side(dseq):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("temp error")
            return [_make_bid("akash1prov", 50)]

        client.get_bids.side_effect = bids_side
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        result = deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)
        assert result["provider"] == "akash1prov"


class TestDeployNoProviderInBid:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_raises_when_bid_has_no_provider(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [
            {"price": {"amount": 10, "denom": "uakt"}, "state": "open"}
        ]
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        with pytest.raises(RuntimeError, match="no provider address"):
            deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)


class TestDeployAllowedProviderNoBidWithDiagnostics:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_warns_when_allowed_provider_no_bid(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.setenv("AKASH_PROVIDERS", "akash1allowed,akash1slow")
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [_make_bid("akash1allowed", 100)]
        client.get_provider.return_value = {
            "isOnline": True,
            "isValidVersion": True,
            "uptime1d": 99.5,
            "stats": {
                "cpu": {"available": 10, "active": 5},
                "memory": {"available": 20, "active": 10},
            },
        }
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        result = deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)
        assert result["provider"] == "akash1allowed"
        client.get_provider.assert_called_with("akash1slow")

    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_provider_not_found_in_registry(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.setenv("AKASH_PROVIDERS", "akash1allowed,akash1missing")
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [_make_bid("akash1allowed", 100)]
        client.get_provider.return_value = None
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        result = deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)
        assert result["provider"] == "akash1allowed"

    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_provider_query_fails(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.setenv("AKASH_PROVIDERS", "akash1allowed,akash1error")
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        client.get_bids.return_value = [_make_bid("akash1allowed", 100)]
        client.get_provider.side_effect = RuntimeError("query failed")
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        result = deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)
        assert result["provider"] == "akash1allowed"


class TestDeployRetryPhase:
    @patch("just_akash.deploy.time")
    @patch("just_akash.deploy.AkashConsoleAPI")
    def test_no_bids_phase1_then_bids_phase2(self, MockAPI, mock_time, tmp_path, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.delenv("AKASH_PROVIDERS", raising=False)
        sdl_file = tmp_path / "sdl.yaml"
        sdl_file.write_text(SDL_YAML)

        client = MockAPI.return_value
        client.create_deployment.return_value = {"dseq": "12345", "manifest": "abc"}
        call_count = [0]

        def bids_side(dseq):
            call_count[0] += 1
            if call_count[0] <= 1:
                return []
            return [_make_bid("akash1prov", 75)]

        client.get_bids.side_effect = bids_side
        client.create_lease.return_value = {"data": {"lease": "created"}}

        t = _time_mock()
        mock_time.time.side_effect = t
        mock_time.sleep.return_value = None

        result = deploy(sdl_path=str(sdl_file), bid_wait=10, bid_wait_retry=10)
        assert result["provider"] == "akash1prov"
