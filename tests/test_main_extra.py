"""Additional tests for __main__.py to improve coverage."""

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mops.__main__ import (
    _run_components,
    _setup_logger,
    main,
)


class TestSetupLogger:
    def test_logger_sets_up(self):
        with patch("mops.__main__.logger") as mock_logger:
            _setup_logger()
            mock_logger.remove.assert_called_once()
            assert mock_logger.add.call_count == 2  # stderr + file


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
            _run_components("server", server_port=10080, client_port=10081, api_port=10082,
                            listen="127.0.0.1", advertise="", strategy="random", weight=1)


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
            _run_components("client", server_port=10080, client_port=10081, api_port=10082,
                            listen="127.0.0.1", advertise="", strategy="random", weight=1)


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
            _run_components("both", server_port=10080, client_port=10081, api_port=10082,
                            listen="127.0.0.1", advertise="", strategy="random", weight=1)


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
                cmd_dashboard(Namespace(port=10100))
                mock_cls.assert_called_once_with(port=10100)
                mock_run.assert_called_once()


class TestConfigLoading:
    def test_main_with_config_file(self):
        with patch("sys.argv", ["mops", "run", "-c", "test.json"]), \
             patch("mops.__main__._load_config_file", return_value={
                 "mode": "server", "server_port": 20080, "client_port": 20090,
                 "api_port": 20100, "strategy": "hash",
             }), \
             patch("mops.__main__._run_components") as mock_run:
            main()
            mock_run.assert_called_once()
            call_kwargs = mock_run.call_args[1]
            assert call_kwargs["mode"] == "server"
            assert call_kwargs["server_port"] == 20080

    def test_main_proxy_no_action_shows_help(self):
        with patch("sys.argv", ["mops", "proxy"]), \
             patch("mops.__main__.build_parser") as mock_build:
            mock_parser = MagicMock()
            mock_build.return_value = mock_parser
            mock_args = Namespace(command="proxy", proxy_action=None)
            mock_parser.parse_args.return_value = mock_args
            with pytest.raises(SystemExit):
                main()

    def test_apply_config_overrides_defaults(self):
        from mops.__main__ import _apply_config
        from argparse import Namespace
        # Args start as None (as argparse now does with None defaults)
        args = Namespace(mode=None, server_port=None, client_port=None, api_port=None,
                        listen=None, advertise=None, strategy=None, weight=None)
        cfg = {"mode": "server", "server_port": 20080, "strategy": "hash"}
        _apply_config(args, cfg)
        assert args.mode == "server"
        assert args.server_port == 20080
        assert args.strategy == "hash"
        # Unchanged fields remain None (will be filled by _apply_defaults later)
        assert args.client_port is None
        assert args.listen is None


class TestDaemonize:
    def test_daemonize_calls_popen(self):
        from mops.__main__ import _daemonize
        from argparse import Namespace
        args = Namespace(mode="both", server_port=10080, client_port=10081,
                        api_port=10082, listen="127.0.0.1", advertise="",
                        strategy="random", weight=1, config=None)
        with patch("sys.platform", "win32"), \
             patch("shutil.which", return_value="/usr/bin/uv"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("mops.__main__.LOG_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(return_value=MagicMock(
                write_text=MagicMock()))
            mock_popen.return_value = MagicMock(pid=12345)
            _daemonize(args)
            cmd = mock_popen.call_args[0][0]
            assert "uv" in cmd[0] or "python" in cmd[0]

    def test_daemonize_with_config(self):
        from mops.__main__ import _daemonize
        from argparse import Namespace
        args = Namespace(mode="server", server_port=20080, client_port=20090,
                        api_port=20100, listen="0.0.0.0", advertise="10.0.0.1",
                        strategy="hash", weight=2, config="/path/config.json")
        with patch("sys.platform", "win32"), \
             patch("shutil.which", return_value="/usr/bin/uv"), \
             patch("subprocess.Popen") as mock_popen, \
             patch("mops.__main__.LOG_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(return_value=MagicMock(
                write_text=MagicMock()))
            mock_popen.return_value = MagicMock(pid=99)
            _daemonize(args)
            cmd = mock_popen.call_args[0][0]
            assert "-c" in cmd
            assert "/path/config.json" in cmd
