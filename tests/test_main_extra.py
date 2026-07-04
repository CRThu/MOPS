"""Additional tests for __main__.py to improve coverage."""

import json
from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, patch

from mops.__main__ import (
    _run_async,
    _run_both,
    _run_client,
    _run_server,
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


class TestRunAsync:
    @patch("mops.__main__.asyncio.run")
    def test_run_async_calls_run_and_handles_stop(self, mock_run):
        mock_run.side_effect = lambda coro: coro.close() or None
        mock_obj = MagicMock()
        _run_async(lambda: mock_obj)
        mock_run.assert_called_once()


class TestRunServer:
    @patch("mops.__main__.asyncio.run")
    def test_run_server_calls_asyncio_run(self, mock_run):
        mock_run.side_effect = lambda coro: coro.close() or None
        _run_server(base_port=10080, weight=1)
        mock_run.assert_called_once()


class TestRunClient:
    @patch("mops.__main__.asyncio.run")
    def test_run_client_calls_asyncio_run(self, mock_run):
        mock_run.side_effect = lambda coro: coro.close() or None
        _run_client(base_port=10080, listen="127.0.0.1", strategy="random")
        mock_run.assert_called_once()


class TestRunBoth:
    @patch("mops.__main__.asyncio.run")
    def test_run_both_creates_all(self, mock_run):
        mock_run.side_effect = lambda coro: coro.close() or None
        with patch("mops.server.MopsServer"), \
             patch("mops.client.MopsClient"), \
             patch("mops.api.MopsApi"):
            _run_both(base_port=10080, listen="127.0.0.1", strategy="random", weight=1)
            mock_run.assert_called_once()


class TestServiceLog:
    def test_log_no_file(self, capsys):
        with patch("mops.__main__.LOG_DIR") as mock_dir:
            mock_dir.__truediv__ = lambda self, x: Path("/nonexistent/mops.log")
            cmd_service_log(Namespace(lines=50, search=""))
            captured = capsys.readouterr()
            assert "No log file" in captured.out

    def test_log_with_content(self, capsys, tmp_path):
        log_file = tmp_path / "mops.log"
        log_file.write_text("line1\nline2\nline3\n", encoding="utf-8")
        with patch("mops.__main__.LOG_DIR") as mock_dir:
            mock_dir.__truediv__ = lambda self, x: log_file
            cmd_service_log(Namespace(lines=2, search=""))
            captured = capsys.readouterr()
            assert "line2" in captured.out
            assert "line3" in captured.out
            assert "line1" not in captured.out

    def test_log_with_search(self, capsys, tmp_path):
        log_file = tmp_path / "mops.log"
        log_file.write_text("info msg\nerror msg\ninfo again\n", encoding="utf-8")
        with patch("mops.__main__.LOG_DIR") as mock_dir:
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
