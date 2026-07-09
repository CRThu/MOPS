"""Tests for CLI entry point (__main__.py)."""

from unittest.mock import patch

import pytest

from mops.__main__ import build_parser, main


class TestBuildParser:
    def test_run_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["run"])
        assert args.command == "run"
        assert args.mode == "both"
        assert args.port == 10080
        assert args.strategy == "random"
        assert args.weight == 1

    def test_run_server_mode(self):
        parser = build_parser()
        args = parser.parse_args(["run", "server"])
        assert args.mode == "server"

    def test_run_client_mode(self):
        parser = build_parser()
        args = parser.parse_args(["run", "client", "--listen", "0.0.0.0", "--port", "20080"])
        assert args.mode == "client"
        assert args.listen == "0.0.0.0"
        assert args.port == 20080

    def test_run_both_mode(self):
        parser = build_parser()
        args = parser.parse_args(["run", "both", "--strategy", "hash"])
        assert args.mode == "both"
        assert args.strategy == "hash"

    def test_service_install_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["service", "install"])
        assert args.command == "service"
        assert args.service_action == "install"

    def test_service_uninstall_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["service", "uninstall"])
        assert args.command == "service"
        assert args.service_action == "uninstall"

    def test_service_start_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["service", "start", "--mode", "server", "--port", "30080", "--strategy", "hash"])
        assert args.command == "service"
        assert args.service_action == "start"
        assert args.mode == "server"
        assert args.port == 30080
        assert args.strategy == "hash"

    def test_service_start_subcommand_defaults(self):
        parser = build_parser()
        args = parser.parse_args(["service", "start"])
        assert args.mode == "both"
        assert args.port == 10080
        assert args.strategy == "random"

    def test_service_stop_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["service", "stop"])
        assert args.command == "service"
        assert args.service_action == "stop"

    def test_service_status_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["service", "status"])
        assert args.command == "service"
        assert args.service_action == "status"

    def test_service_log_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["service", "log"])
        assert args.command == "service"
        assert args.service_action == "log"
        assert args.lines == 50
        assert args.search == ""

    def test_service_log_with_options(self):
        parser = build_parser()
        args = parser.parse_args(["service", "log", "-n", "100", "-s", "error"])
        assert args.lines == 100
        assert args.search == "error"

    def test_proxy_on_subcommand(self):
        parser = build_parser()
        args = parser.parse_args(["proxy", "on"])
        assert args.command == "proxy"
        assert args.proxy_action == "on"
        assert args.port == 10081

    def test_proxy_on_custom_port(self):
        parser = build_parser()
        args = parser.parse_args(["proxy", "on", "--port", "8080"])
        assert args.port == 8080

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


class TestMain:
    def test_no_command_defaults_to_run_both(self):
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
        with patch("sys.argv", ["mops", "run", "server"]), \
             patch("mops.__main__.cmd_run") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_service_install_command(self):
        with patch("sys.argv", ["mops", "service", "install"]), \
             patch("mops.__main__.cmd_install") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_service_uninstall_command(self):
        with patch("sys.argv", ["mops", "service", "uninstall"]), \
             patch("mops.__main__.cmd_uninstall") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_service_start_command(self):
        with patch("sys.argv", ["mops", "service", "start"]), \
             patch("mops.__main__.cmd_start") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_service_stop_command(self):
        with patch("sys.argv", ["mops", "service", "stop"]), \
             patch("mops.__main__.cmd_stop") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_service_status_command(self):
        with patch("sys.argv", ["mops", "service", "status"]), \
             patch("mops.__main__.cmd_status") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_service_log_command(self):
        with patch("sys.argv", ["mops", "service", "log"]), \
             patch("mops.__main__.cmd_service_log") as mock_cmd:
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
        args = Namespace(mode="both", port=10080, strategy="random", service=False, listen="127.0.0.1", weight=1, bind="")
        cmd_run(args)
        mock_run.assert_called_once()

    @patch("mops.__main__._run_components")
    def test_cmd_run_server(self, mock_run):
        from mops.__main__ import cmd_run
        from argparse import Namespace
        args = Namespace(mode="server", port=10080, strategy="random", service=False, listen="127.0.0.1", weight=1, bind="")
        cmd_run(args)
        mock_run.assert_called_once()

    @patch("mops.__main__._run_components")
    def test_cmd_run_client(self, mock_run):
        from mops.__main__ import cmd_run
        from argparse import Namespace
        args = Namespace(mode="client", port=10080, strategy="random", service=False, listen="127.0.0.1", weight=1, bind="")
        cmd_run(args)
        mock_run.assert_called_once()

    def test_cmd_install(self):
        from mops.__main__ import cmd_install
        from argparse import Namespace
        args = Namespace()
        with patch("mops.service.install") as mock_install:
            cmd_install(args)
            mock_install.assert_called_once()

    def test_cmd_uninstall(self):
        from mops.__main__ import cmd_uninstall
        from argparse import Namespace
        args = Namespace()
        with patch("mops.service.uninstall"):
            cmd_uninstall(args)

    def test_cmd_start(self):
        from mops.__main__ import cmd_start
        from argparse import Namespace
        args = Namespace(mode="both", port=10080, strategy="random", bind="")
        with patch("mops.service.start") as mock_start:
            cmd_start(args)
            mock_start.assert_called_once_with(mode="both", port=10080, strategy="random", bind="")

    def test_cmd_stop(self):
        from mops.__main__ import cmd_stop
        from argparse import Namespace
        args = Namespace()
        with patch("mops.service.stop"):
            cmd_stop(args)

    def test_cmd_status(self):
        from mops.__main__ import cmd_status
        from argparse import Namespace
        args = Namespace()
        with patch("mops.service.status", return_value={"running": True}):
            cmd_status(args)

    def test_cmd_proxy_on(self):
        from mops.__main__ import cmd_proxy_on
        from argparse import Namespace
        args = Namespace(port=9090)
        with patch("mops.__main__.proxy_on") as mock_on:
            cmd_proxy_on(args)
            mock_on.assert_called_once_with(9090)

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
