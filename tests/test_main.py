"""Tests for CLI entry point (__main__.py)."""

import signal
from unittest.mock import MagicMock, patch

import pytest

from mops.__main__ import build_parser, main, _apply_defaults


class TestBuildParser:
    def test_run_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["run"])
        _apply_defaults(args)
        assert args.command == "run"
        assert args.mode == "both"
        assert args.server_port == 10080
        assert args.client_port == 10081
        assert args.api_port == 10082
        assert args.strategy == "random"
        assert args.weight == 1

    def test_run_server_mode(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--mode", "server"])
        assert args.mode == "server"

    def test_run_client_mode(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--mode", "client", "--listen", "0.0.0.0", "--client-port", "10090"])
        assert args.mode == "client"
        assert args.listen == "0.0.0.0"
        assert args.client_port == 10090

    def test_run_both_mode(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--mode", "both", "--strategy", "hash"])
        assert args.mode == "both"
        assert args.strategy == "hash"

    def test_run_explicit_ports(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--server-port", "20080", "--client-port", "20090", "--api-port", "20100"])
        assert args.server_port == 20080
        assert args.client_port == 20090
        assert args.api_port == 20100

    def test_run_advertise(self):
        parser = build_parser()
        args = parser.parse_args(["run", "--advertise", "192.168.1.5"])
        assert args.advertise == "192.168.1.5"

    def test_run_config_file(self):
        parser = build_parser()
        args = parser.parse_args(["run", "-c", "config.json"])
        assert args.config == "config.json"

    def test_run_background_flag(self):
        parser = build_parser()
        args = parser.parse_args(["run", "-b"])
        assert args.background is True

    def test_stop_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["stop"])
        assert args.command == "stop"

    def test_proxy_on_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["proxy", "on"])
        assert args.command == "proxy"
        assert args.proxy_action == "on"
        assert args.host is None
        assert args.port is None

    def test_proxy_on_custom_port(self):
        parser = build_parser()
        args = parser.parse_args(["proxy", "on", "--port", "8080"])
        assert args.port == 8080

    def test_proxy_on_target(self):
        parser = build_parser()
        args = parser.parse_args(["proxy", "on", "192.168.1.100:20081"])
        assert args.target == "192.168.1.100:20081"

    def test_proxy_on_host_and_port(self):
        parser = build_parser()
        args = parser.parse_args(["proxy", "on", "--host", "192.168.1.100", "--port", "20081"])
        assert args.host == "192.168.1.100"
        assert args.port == 20081

    def test_proxy_off_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["proxy", "off"])
        assert args.command == "proxy"
        assert args.proxy_action == "off"

    def test_proxy_status_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["proxy", "status"])
        assert args.command == "proxy"
        assert args.proxy_action == "status"

    def test_dashboard_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["dashboard"])
        assert args.command == "dashboard"
        assert args.port == 10100

    def test_dashboard_custom_port(self):
        parser = build_parser()
        args = parser.parse_args(["dashboard", "--port", "8080"])
        assert args.port == 8080


class TestMain:
    def test_no_command_defaults_to_run(self):
        with patch("sys.argv", ["mops"]), \
             patch("mops.__main__.cmd_run") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_run_command(self):
        with patch("sys.argv", ["mops", "run"]), \
             patch("mops.__main__.cmd_run") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_run_server_command(self):
        with patch("sys.argv", ["mops", "run", "--mode", "server"]), \
             patch("mops.__main__.cmd_run") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_proxy_on_command(self):
        with patch("sys.argv", ["mops", "proxy", "on"]), \
             patch("mops.__main__.cmd_proxy_on") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_proxy_off_command(self):
        with patch("sys.argv", ["mops", "proxy", "off"]), \
             patch("mops.__main__.cmd_proxy_off") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_proxy_status_command(self):
        with patch("sys.argv", ["mops", "proxy", "status"]), \
             patch("mops.__main__.cmd_proxy_status") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


class TestCmdFunctions:
    @patch("mops.__main__._run_components")
    def test_cmd_run_both(self, mock_run):
        from mops.__main__ import cmd_run
        from argparse import Namespace
        args = Namespace(mode="both", server_port=10080, client_port=10081, api_port=10082,
                        strategy="random", listen="127.0.0.1", weight=1, advertise="",
                        background=False, config=None)
        cmd_run(args)
        mock_run.assert_called_once()

    @patch("mops.__main__._run_components")
    def test_cmd_run_server(self, mock_run):
        from mops.__main__ import cmd_run
        from argparse import Namespace
        args = Namespace(mode="server", server_port=10080, client_port=10081, api_port=10082,
                        strategy="random", listen="127.0.0.1", weight=1, advertise="",
                        background=False, config=None)
        cmd_run(args)
        mock_run.assert_called_once()

    @patch("mops.__main__._run_components")
    def test_cmd_run_client(self, mock_run):
        from mops.__main__ import cmd_run
        from argparse import Namespace
        args = Namespace(mode="client", server_port=10080, client_port=10081, api_port=10082,
                        strategy="random", listen="127.0.0.1", weight=1, advertise="",
                        background=False, config=None)
        cmd_run(args)
        mock_run.assert_called_once()

    def test_cmd_proxy_on(self):
        from mops.__main__ import cmd_proxy_on
        from argparse import Namespace
        args = Namespace(target=None, host=None, port=9090)
        with patch("mops.__main__.proxy_on") as mock_on:
            cmd_proxy_on(args)
            mock_on.assert_called_once_with("127.0.0.1", 9090)

    def test_cmd_proxy_on_target(self):
        from mops.__main__ import cmd_proxy_on
        from argparse import Namespace
        args = Namespace(target="192.168.1.100:20081", host=None, port=None)
        with patch("mops.__main__.proxy_on") as mock_on:
            cmd_proxy_on(args)
            mock_on.assert_called_once_with("192.168.1.100", 20081)

    def test_cmd_proxy_on_host_override(self):
        from mops.__main__ import cmd_proxy_on
        from argparse import Namespace
        args = Namespace(target="10.0.0.1:10081", host="192.168.1.100", port=None)
        with patch("mops.__main__.proxy_on") as mock_on:
            cmd_proxy_on(args)
            mock_on.assert_called_once_with("192.168.1.100", 10081)

    def test_cmd_proxy_off(self):
        from mops.__main__ import cmd_proxy_off
        from argparse import Namespace
        args = Namespace()
        with patch("mops.__main__.proxy_off") as mock_off:
            cmd_proxy_off(args)
            mock_off.assert_called_once()

    def test_cmd_proxy_status(self, capsys):
        from mops.__main__ import cmd_proxy_status
        from argparse import Namespace
        args = Namespace()
        with patch("mops.__main__.proxy_status", return_value={"enabled": True}):
            cmd_proxy_status(args)
            captured = capsys.readouterr()
            assert '"enabled": true' in captured.out


class TestCmdStop:
    def test_stop_no_pid_file(self, capsys):
        from mops.__main__ import cmd_stop
        from argparse import Namespace
        with patch("mops.__main__.LOG_DIR") as mock_dir:
            mock_pid_file = mock_dir.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
            cmd_stop(Namespace())
            captured = capsys.readouterr()
            assert "No PID file" in captured.out

    def test_stop_with_pid(self, capsys, tmp_path):
        from mops.__main__ import cmd_stop
        from argparse import Namespace
        pid_file = tmp_path / "mops.pid"
        pid_file.write_text("12345")
        with patch("mops.__main__.LOG_DIR", tmp_path), \
             patch("mops.__main__._is_alive", return_value=True), \
             patch("sys.platform", "linux"), \
             patch("os.kill") as mock_kill:
            cmd_stop(Namespace())
            mock_kill.assert_called_once_with(12345, signal.SIGTERM)
            captured = capsys.readouterr()
            assert "stopped" in captured.out
            assert not pid_file.exists()

    def test_stop_already_dead(self, capsys, tmp_path):
        from mops.__main__ import cmd_stop
        from argparse import Namespace
        pid_file = tmp_path / "mops.pid"
        pid_file.write_text("99999")
        with patch("mops.__main__.LOG_DIR", tmp_path), \
             patch("mops.__main__._is_alive", return_value=False):
            cmd_stop(Namespace())
            captured = capsys.readouterr()
            assert "not found" in captured.out
            assert not pid_file.exists()
