"""Additional tests for __main__.py to improve coverage."""

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mops.__main__ import (
    _run_components,
    _setup_logger,
    cmd_service_log,
    main,
)


class TestSetupLogger:
    def test_service_mode(self):
        with patch("mops.__main__.logger") as mock_logger:
            _setup_logger(service_mode=True)
            mock_logger.remove.assert_called_once()
            assert mock_logger.add.call_count == 2  # stderr + file
            levels = [call[1]["level"] for call in mock_logger.add.call_args_list]
            assert "INFO" in levels

    def test_interactive_mode(self):
        with patch("mops.__main__.logger") as mock_logger:
            _setup_logger(service_mode=False)
            mock_logger.remove.assert_called_once()
            assert mock_logger.add.call_count == 2  # stderr + file
            levels = [call[1]["level"] for call in mock_logger.add.call_args_list]
            assert "DEBUG" in levels


class TestRunServer:
    @pytest.mark.asyncio
    async def test_run_server_creates_api(self):
        """Verify _run_components with mode='server' creates MopsApi correctly."""
        async def exec_coro(coro):
            with patch("mops.server.MopsServer") as mock_server_cls, \
                 patch("mops.api.MopsApi") as mock_api_cls:
                mock_server = AsyncMock()
                mock_server_cls.return_value = mock_server
                mock_api = AsyncMock()
                mock_api_cls.return_value = mock_api

                try:
                    await coro
                except Exception:
                    pass

                mock_api_cls.assert_called_once()
                call_kwargs = mock_api_cls.call_args[1]
                assert call_kwargs["mode"] == "server"
                assert call_kwargs["port"] == 10082
                assert "server_stats" in call_kwargs

        with patch("mops.__main__.asyncio.run", side_effect=exec_coro):
            _run_components("server", base_port=10080, listen="127.0.0.1", strategy="random", weight=1, bind="")


class TestRunClient:
    @pytest.mark.asyncio
    async def test_run_client_creates_api(self):
        """Verify _run_components with mode='client' creates MopsApi correctly."""
        async def exec_coro(coro):
            with patch("mops.client.MopsClient") as mock_client_cls, \
                 patch("mops.api.MopsApi") as mock_api_cls:
                mock_client = AsyncMock()
                mock_client_cls.return_value = mock_client
                mock_api = AsyncMock()
                mock_api_cls.return_value = mock_api

                try:
                    await coro
                except Exception:
                    pass

                mock_api_cls.assert_called_once()
                call_kwargs = mock_api_cls.call_args[1]
                assert call_kwargs["mode"] == "client"
                assert call_kwargs["port"] == 10082
                assert "client_stats" in call_kwargs

        with patch("mops.__main__.asyncio.run", side_effect=exec_coro):
            _run_components("client", base_port=10080, listen="127.0.0.1", strategy="random", weight=1, bind="")


class TestRunBoth:
    @pytest.mark.asyncio
    async def test_run_both_creates_api_with_both_stats(self):
        """Verify _run_components with mode='both' creates MopsApi with both stats."""
        async def exec_coro(coro):
            with patch("mops.server.MopsServer"), \
                 patch("mops.client.MopsClient"), \
                 patch("mops.api.MopsApi") as mock_api_cls:
                mock_api = AsyncMock()
                mock_api_cls.return_value = mock_api

                try:
                    await coro
                except Exception:
                    pass

                mock_api_cls.assert_called_once()
                call_kwargs = mock_api_cls.call_args[1]
                assert call_kwargs["mode"] == "both"
                assert "server_stats" in call_kwargs
                assert "client_stats" in call_kwargs

        with patch("mops.__main__.asyncio.run", side_effect=exec_coro):
            _run_components("both", base_port=10080, listen="127.0.0.1", strategy="random", weight=1, bind="")


class TestServiceLog:
    def test_log_no_file(self, capsys):
        with patch("mops.service.LOG_DIR") as mock_dir:
            mock_dir.__truediv__ = lambda self, x: Path("/nonexistent/mops.log")
            cmd_service_log(Namespace(lines=50, search=""))
            captured = capsys.readouterr()
            assert "No log file" in captured.out

    def test_log_with_content(self, capsys, tmp_path):
        log_file = tmp_path / "mops.log"
        log_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
        with patch("mops.service.LOG_DIR") as mock_dir:
            mock_dir.__truediv__ = lambda self, x: log_file
            cmd_service_log(Namespace(lines=2, search=""))
            captured = capsys.readouterr()
            assert "line2" in captured.out
            assert "line3" in captured.out
            assert "line1" not in captured.out

    def test_log_with_search(self, capsys, tmp_path):
        log_file = tmp_path / "mops.log"
        log_file.write_text("info msg\nerror msg\ninfo again\n", encoding="utf-8")
        with patch("mops.service.LOG_DIR") as mock_dir:
            mock_dir.__truediv__ = lambda self, x: log_file
            cmd_service_log(Namespace(lines=50, search="error"))
            captured = capsys.readouterr()
            assert "error msg" in captured.out
            assert "info msg" not in captured.out


class TestProxyIntegration:
    def test_proxy_on_dispatches(self):
        with patch("sys.argv", ["mops", "proxy", "on"]), \
             patch("mops.__main__.cmd_proxy_on") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_proxy_off_dispatches(self):
        with patch("sys.argv", ["mops", "proxy", "off"]), \
             patch("mops.__main__.cmd_proxy_off") as mock_cmd:
            main()
            mock_cmd.assert_called_once()

    def test_proxy_status_dispatches(self):
        with patch("sys.argv", ["mops", "proxy", "status"]), \
             patch("mops.__main__.cmd_proxy_status") as mock_cmd:
            main()
            mock_cmd.assert_called_once()


class TestCmdDashboard:
    def test_cmd_dashboard(self):
        from mops.__main__ import cmd_dashboard
        with patch("mops.dashboard.MopsDashboard") as mock_cls:
            mock_inst = AsyncMock()
            mock_cls.return_value = mock_inst
            with patch("mops.__main__.asyncio.run") as mock_run:
                cmd_dashboard(Namespace(port=10082, service=False))
                mock_cls.assert_called_once_with(port=10082)
                mock_run.assert_called_once()


class TestServiceConfigLoading:
    def test_main_service_mode_loads_config(self):
        with patch("sys.argv", ["mops", "run", "--service"]), \
             patch("mops.service._load_config", return_value={
                 "mode": "server", "port": 10090, "strategy": "hash", "bind": "1.2.3.4"
             }), \
             patch("mops.__main__._run_components") as mock_run:
            main()
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            assert args[0] == "server"  # mode
            assert args[1] == 10090  # base_port

    def test_main_service_no_action_shows_help(self):
        with patch("sys.argv", ["mops", "service"]), \
             patch("mops.__main__.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_args = Namespace(command="service", service_action=None, service=False)
            mock_parser.parse_args.return_value = mock_args
            with pytest.raises(SystemExit):
                main()

    def test_main_proxy_no_action_shows_help(self):
        with patch("sys.argv", ["mops", "proxy"]), \
             patch("mops.__main__.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_args = Namespace(command="proxy", proxy_action=None, service=False)
            mock_parser.parse_args.return_value = mock_args
            with pytest.raises(SystemExit):
                main()
