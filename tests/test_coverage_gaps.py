"""Tests for coverage gaps — interactive picker, JSON output, confirm helper."""

import sys
import termios
import tty
from unittest.mock import patch

import pytest

from just_akash.api import (
    AkashConsoleAPI,
    _confirm,
    _interactive_pick,
    _json_output,
    _save_tags,
    format_deployments_json,
)


class TestConfirm:
    def test_yes_flag_skips_prompt(self):
        assert _confirm("prompt? ", yes=True) is True

    @patch("builtins.input", return_value="y")
    def test_user_confirms(self, mock_input):
        assert _confirm("prompt? ") is True
        mock_input.assert_called_once_with("prompt? ")

    @patch("builtins.input", return_value="n")
    def test_user_declines(self, mock_input):
        assert _confirm("prompt? ") is False

    @patch("builtins.input", return_value="")
    def test_user_empty(self, mock_input):
        assert _confirm("prompt? ") is False


class TestJsonOutput:
    def test_dict(self):
        result = _json_output({"key": "value"})
        assert '"key": "value"' in result

    def test_list(self):
        result = _json_output([1, 2, 3])
        assert "[\n  1" in result


class TestFormatDeploymentsJson:
    def test_empty(self, tmp_path, monkeypatch):
        from just_akash import api

        monkeypatch.setattr(api, "TAGS_FILE", tmp_path / ".tags.json")
        result = format_deployments_json([])
        assert result == "[]"

    def test_single_deployment_with_ssh(self, tmp_path, monkeypatch):
        from just_akash import api

        monkeypatch.setattr(api, "TAGS_FILE", tmp_path / ".tags.json")
        _save_tags({"12345": "my-job"})
        dep = {
            "dseq": "12345",
            "deployment": {"state": "active"},
            "leases": [
                {
                    "id": {"provider": "akash1prov"},
                    "status": {
                        "forwarded_ports": {
                            "ssh": [{"port": 22, "host": "1.2.3.4", "externalPort": 2222}]
                        }
                    },
                }
            ],
        }
        result = format_deployments_json([dep])
        assert '"dseq": "12345"' in result
        assert '"tag": "my-job"' in result
        assert '"state": "active"' in result
        assert '"provider": "akash1prov"' in result
        assert '"ssh": "1.2.3.4:2222"' in result

    def test_deployment_no_ssh(self, tmp_path, monkeypatch):
        from just_akash import api

        monkeypatch.setattr(api, "TAGS_FILE", tmp_path / ".tags.json")
        dep = {
            "dseq": "12345",
            "deployment": {"state": "active"},
            "leases": [],
        }
        result = format_deployments_json([dep])
        assert '"ssh": null' in result


def _make_tty_pick_test(reads, deployments, tmp_path, monkeypatch):
    from just_akash import api

    monkeypatch.setattr(api, "TAGS_FILE", tmp_path / ".tags.json")
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)

    monkeypatch.setattr(sys.stdin, "fileno", lambda: 0)

    read_iter = iter(reads)

    monkeypatch.setattr(termios, "tcgetattr", lambda fd: [])
    monkeypatch.setattr(termios, "TCSADRAIN", 1)
    monkeypatch.setattr(termios, "tcsetattr", lambda fd, when, attrs: None)
    monkeypatch.setattr(tty, "setraw", lambda fd: None)
    monkeypatch.setattr(sys.stdin, "read", lambda n=1: next(read_iter))

    client = AkashConsoleAPI("key")
    return _interactive_pick(deployments, client)


class TestInteractivePickTty:
    def test_enter_selects_first(self, tmp_path, monkeypatch):
        deployments = [
            {
                "dseq": "11111",
                "deployment": {"state": "active"},
                "leases": [{"id": {"provider": "akash1prov"}}],
            },
            {"dseq": "22222", "deployment": {"state": "active"}, "leases": []},
        ]
        result = _make_tty_pick_test(["\r"], deployments, tmp_path, monkeypatch)
        assert result == "11111"

    def test_arrow_down_then_enter(self, tmp_path, monkeypatch):
        deployments = [
            {"dseq": "11111", "deployment": {"state": "active"}, "leases": []},
            {"dseq": "22222", "deployment": {"state": "active"}, "leases": []},
        ]
        result = _make_tty_pick_test(["\x1b", "[B", "\r"], deployments, tmp_path, monkeypatch)
        assert result == "22222"

    def test_arrow_up_wraps(self, tmp_path, monkeypatch):
        deployments = [
            {"dseq": "11111", "deployment": {"state": "active"}, "leases": []},
            {"dseq": "22222", "deployment": {"state": "active"}, "leases": []},
        ]
        result = _make_tty_pick_test(["\x1b", "[A", "\r"], deployments, tmp_path, monkeypatch)
        assert result == "22222"

    def test_q_cancels(self, tmp_path, monkeypatch):
        deployments = [
            {"dseq": "11111", "deployment": {"state": "active"}, "leases": []},
        ]
        with pytest.raises(SystemExit) as exc_info:
            _make_tty_pick_test(["q"], deployments, tmp_path, monkeypatch)
        assert exc_info.value.code == 0

    def test_ctrl_c_cancels(self, tmp_path, monkeypatch):
        deployments = [
            {"dseq": "11111", "deployment": {"state": "active"}, "leases": []},
        ]
        with pytest.raises(SystemExit) as exc_info:
            _make_tty_pick_test(["\x03"], deployments, tmp_path, monkeypatch)
        assert exc_info.value.code == 0

    def test_with_tags_and_ssh(self, tmp_path, monkeypatch):
        _save_tags({"11111": "my-deploy"})
        deployments = [
            {
                "dseq": "11111",
                "deployment": {"state": "active"},
                "leases": [
                    {
                        "id": {"provider": "akash1prov"},
                        "status": {
                            "forwarded_ports": {
                                "ssh": [{"port": 22, "host": "1.2.3.4", "externalPort": 2222}]
                            }
                        },
                    }
                ],
            },
        ]
        result = _make_tty_pick_test(["\r"], deployments, tmp_path, monkeypatch)
        assert result == "11111"

    def test_escape_unknown_key_ignored(self, tmp_path, monkeypatch):
        deployments = [
            {"dseq": "11111", "deployment": {"state": "active"}, "leases": []},
            {"dseq": "22222", "deployment": {"state": "active"}, "leases": []},
        ]
        result = _make_tty_pick_test(["\x1b", "[C", "\r"], deployments, tmp_path, monkeypatch)
        assert result == "11111"


class TestGetProviderResponseShapes:
    @patch.object(AkashConsoleAPI, "_request")
    def test_bare_list(self, mock_req):
        mock_req.return_value = [{"owner": "akash1target", "isOnline": True}]
        client = AkashConsoleAPI("key")
        result = client.get_provider("akash1target")
        assert result is not None
        assert result["owner"] == "akash1target"

    @patch.object(AkashConsoleAPI, "_request")
    def test_nested_dict(self, mock_req):
        mock_req.return_value = {
            "data": {"providers": [{"owner": "akash1target", "isOnline": True}]}
        }
        client = AkashConsoleAPI("key")
        result = client.get_provider("akash1target")
        assert result is not None

    @patch.object(AkashConsoleAPI, "_request")
    def test_non_dict_non_list(self, mock_req):
        mock_req.return_value = "not a valid response"
        client = AkashConsoleAPI("key")
        result = client.get_provider("akash1target")
        assert result is None

    @patch.object(AkashConsoleAPI, "_request")
    def test_dict_with_data_list(self, mock_req):
        mock_req.return_value = {"data": [{"owner": "akash1target", "isOnline": True}]}
        client = AkashConsoleAPI("key")
        result = client.get_provider("akash1target")
        assert result is not None
