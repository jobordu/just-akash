"""Tests for just_akash.cli — command dispatch logic."""

import os
import sys
from unittest.mock import patch

import pytest


def _run_cli(monkeypatch, args):
    monkeypatch.setattr(sys, "argv", args)
    from just_akash.cli import main

    return main()


class TestCliNoCommand:
    def test_no_command_prints_help(self, monkeypatch):
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash"])
        assert exc_info.value.code == 0


class TestCliDeploy:
    @patch("just_akash.deploy.deploy")
    def test_deploy_success(self, mock_deploy, monkeypatch):
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "deploy", "--sdl", "test.yaml"])
        assert exc_info.value.code == 0
        mock_deploy.assert_called_once()

    @patch("just_akash.deploy.deploy", side_effect=RuntimeError("deploy failed"))
    def test_deploy_failure(self, mock_deploy, monkeypatch):
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "deploy", "--sdl", "test.yaml"])
        assert exc_info.value.code == 1


class TestCliApiNoApiKey:
    def test_api_no_key(self, monkeypatch, capsys):
        monkeypatch.delenv("AKASH_API_KEY", raising=False)
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "api", "list"])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "AKASH_API_KEY not set" in captured.err


class TestCliApiNoSubcommand:
    @patch("just_akash.api.AkashConsoleAPI")
    def test_api_no_subcommand(self, MockAPI, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "api"])
        assert exc_info.value.code == 0


class TestCliApiList:
    @patch("just_akash.api.format_deployments_table", return_value="table output")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_api_list_tty(self, MockAPI, mock_fmt, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.list_deployments.return_value = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        _run_cli(monkeypatch, ["just-akash", "api", "list"])
        captured = capsys.readouterr()
        assert "table output" in captured.out

    @patch("just_akash.api.AkashConsoleAPI")
    def test_api_list_json(self, MockAPI, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.list_deployments.return_value = []
        _run_cli(monkeypatch, ["just-akash", "api", "list"])
        captured = capsys.readouterr()
        assert "[]" in captured.out


class TestCliApiStatusWithDseq:
    @patch("just_akash.api._extract_ssh_info", return_value=None)
    @patch("just_akash.api._extract_lease_provider", return_value="akash1prov")
    @patch("just_akash.api._get_tag", return_value="my-job")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_status_with_dseq(
        self, MockAPI, mock_tag, mock_lease_prov, mock_ssh, monkeypatch, capsys
    ):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.get_deployment.return_value = {
            "deployment": {"state": "active"},
            "leases": [],
        }
        _run_cli(monkeypatch, ["just-akash", "api", "status", "--dseq", "12345"])
        captured = capsys.readouterr()
        assert "active" in captured.out


class TestCliApiStatusNoDeployments:
    @patch("just_akash.api._resolve_dseq", return_value="")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_status_no_deployments(self, MockAPI, mock_resolve, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.list_deployments.return_value = []
        monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "api", "status"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No active deployments" in captured.out


class TestCliApiCloseNoDeployments:
    @patch("just_akash.api._resolve_dseq", return_value="")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_close_no_deployments(self, MockAPI, mock_resolve, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.list_deployments.return_value = []
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "api", "close"])
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "No active deployments" in captured.out


class TestCliApiCloseAllNoDeployments:
    @patch("just_akash.api.AkashConsoleAPI")
    def test_close_all_no_deployments(self, MockAPI, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.list_deployments.return_value = []
        _run_cli(monkeypatch, ["just-akash", "api", "close-all"])
        captured = capsys.readouterr()
        assert "No deployments to close" in captured.out


class TestCliApiTag:
    @patch("just_akash.api._save_tags")
    @patch("just_akash.api._load_tags", return_value={})
    @patch("just_akash.api.AkashConsoleAPI")
    def test_tag_success(self, MockAPI, mock_load, mock_save, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        _run_cli(monkeypatch, ["just-akash", "api", "tag", "--dseq", "12345", "--name", "my-job"])
        captured = capsys.readouterr()
        assert "Tagged 12345" in captured.out
        mock_save.assert_called_once()

    @patch("just_akash.api.AkashConsoleAPI")
    def test_tag_missing_args(self, MockAPI, monkeypatch):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "api", "tag"])
        assert exc_info.value.code == 1


class TestCliApiRuntimeError:
    @patch("just_akash.api.AkashConsoleAPI")
    def test_api_runtime_error(self, MockAPI, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.list_deployments.side_effect = RuntimeError("API error")
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "api", "list"])
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "API error" in captured.err


class TestCliTest:
    @patch("just_akash.test_lifecycle.main")
    def test_test_command(self, mock_test_main, monkeypatch):
        _run_cli(monkeypatch, ["just-akash", "test"])
        mock_test_main.assert_called_once()


class TestCliApiStatusWithSsh:
    @patch("just_akash.api._extract_ssh_info")
    @patch("just_akash.api._extract_lease_provider", return_value="akash1prov")
    @patch("just_akash.api._get_tag", return_value="")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_status_with_ssh(
        self, MockAPI, mock_tag, mock_lease_prov, mock_ssh, monkeypatch, capsys
    ):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.get_deployment.return_value = {
            "deployment": {"state": "active"},
            "leases": [],
        }
        mock_ssh.return_value = {"host": "1.2.3.4", "port": 22222}
        _run_cli(monkeypatch, ["just-akash", "api", "status", "--dseq", "12345"])
        captured = capsys.readouterr()
        assert "ssh -p 22222" in captured.out


class TestCliApiCloseWithConfirm:
    @patch("just_akash.api._save_tags")
    @patch("just_akash.api._load_tags", return_value={})
    @patch("just_akash.api._resolve_dseq", return_value="12345")
    @patch("just_akash.api._get_tag", return_value="")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_close_confirmed(
        self, MockAPI, mock_tag, mock_resolve, mock_load, mock_save, monkeypatch, capsys
    ):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.setattr("builtins.input", lambda _: "y")
        _run_cli(monkeypatch, ["just-akash", "api", "close", "--dseq", "12345"])
        captured = capsys.readouterr()
        assert "closed" in captured.out

    @patch("just_akash.api._resolve_dseq", return_value="12345")
    @patch("just_akash.api._get_tag", return_value="")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_close_cancelled(self, MockAPI, mock_tag, mock_resolve, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        monkeypatch.setattr("builtins.input", lambda _: "n")
        _run_cli(monkeypatch, ["just-akash", "api", "close", "--dseq", "12345"])
        captured = capsys.readouterr()
        assert "Cancelled" in captured.out


class TestCliApiCloseAllWithConfirm:
    @patch("just_akash.api._extract_dseq", side_effect=["1", "2"])
    @patch("just_akash.api._save_tags")
    @patch("just_akash.api._load_tags", return_value={"1": "a", "2": "b"})
    @patch("just_akash.api.format_deployments_table", return_value="table")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_close_all_confirmed(
        self, MockAPI, mock_fmt, mock_load, mock_save, mock_dseq, monkeypatch, capsys
    ):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.list_deployments.return_value = [{"dseq": "1"}, {"dseq": "2"}]
        monkeypatch.setattr("builtins.input", lambda _: "y")
        _run_cli(monkeypatch, ["just-akash", "api", "close-all"])
        captured = capsys.readouterr()
        assert "All deployments closed" in captured.out

    @patch("just_akash.api.format_deployments_table", return_value="table")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_close_all_cancelled(self, MockAPI, mock_fmt, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.list_deployments.return_value = [{"dseq": "1"}]
        monkeypatch.setattr("builtins.input", lambda _: "n")
        _run_cli(monkeypatch, ["just-akash", "api", "close-all"])
        captured = capsys.readouterr()
        assert "Cancelled" in captured.out


class TestCliDeployPassesArgs:
    @patch("just_akash.deploy.deploy")
    def test_deploy_passes_all_args(self, mock_deploy, monkeypatch):
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(
                monkeypatch,
                [
                    "just-akash",
                    "deploy",
                    "--sdl",
                    "my.yaml",
                    "--gpu",
                    "--image",
                    "ubuntu:22.04",
                    "--bid-wait",
                    "30",
                    "--bid-wait-retry",
                    "60",
                ],
            )
        assert exc_info.value.code == 0
        mock_deploy.assert_called_once_with(
            sdl_path="my.yaml",
            gpu=True,
            image="ubuntu:22.04",
            bid_wait=30,
            bid_wait_retry=60,
        )


class TestCliApiConnect:
    @patch("just_akash.api._extract_ssh_info", return_value={"host": "1.2.3.4", "port": 22})
    @patch("just_akash.api._extract_lease_provider", return_value=None)
    @patch("just_akash.api.AkashConsoleAPI")
    def test_connect_with_key(self, MockAPI, mock_lease, mock_ssh, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.get_deployment.return_value = {
            "deployment": {"state": "active"},
            "leases": [],
        }
        with patch("os.execvp") as mock_exec:
            _run_cli(
                monkeypatch,
                ["just-akash", "api", "connect", "--dseq", "12345", "--key", "/fake/key"],
            )
            mock_exec.assert_called_once()

    @patch("just_akash.api._extract_ssh_info", return_value=None)
    @patch("just_akash.api._extract_lease_provider", return_value=None)
    @patch("just_akash.api._resolve_dseq", return_value="")
    @patch("just_akash.api.AkashConsoleAPI")
    def test_connect_no_deployments(
        self, MockAPI, mock_resolve, mock_lease, mock_ssh, monkeypatch, capsys
    ):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.list_deployments.return_value = []
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "api", "connect"])
        assert exc_info.value.code == 1

    @patch("just_akash.api._extract_ssh_info", return_value=None)
    @patch("just_akash.api._extract_lease_provider", return_value=None)
    @patch("just_akash.api.AkashConsoleAPI")
    def test_connect_no_ssh(self, MockAPI, mock_lease, mock_ssh, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.get_deployment.return_value = {
            "deployment": {"state": "active"},
            "leases": [],
        }
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "api", "connect", "--dseq", "12345"])
        assert exc_info.value.code == 1

    @patch("just_akash.api._extract_ssh_info", return_value={"host": "1.2.3.4", "port": 22})
    @patch("just_akash.api._extract_lease_provider", return_value=None)
    @patch("just_akash.api.AkashConsoleAPI")
    def test_connect_no_key_found(self, MockAPI, mock_lease, mock_ssh, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        client = MockAPI.return_value
        client.get_deployment.return_value = {
            "deployment": {"state": "active"},
            "leases": [],
        }
        monkeypatch.setattr(os.path, "exists", lambda _: False)
        with pytest.raises(SystemExit) as exc_info:
            _run_cli(monkeypatch, ["just-akash", "api", "connect", "--dseq", "12345"])
        assert exc_info.value.code == 1


class TestCliApiUnknownCommand:
    @patch("just_akash.api.AkashConsoleAPI")
    def test_unknown_api_command(self, MockAPI, monkeypatch, capsys):
        monkeypatch.setenv("AKASH_API_KEY", "test-key")
        _run_cli(monkeypatch, ["just-akash", "api", "nonexistent"])
        captured = capsys.readouterr()
        assert "usage:" in captured.out.lower() or captured.out == ""
