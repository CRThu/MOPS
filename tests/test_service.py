"""Tests for system service management (service.py)."""

from pathlib import Path
from unittest.mock import MagicMock, patch, AsyncMock
import subprocess

import pytest

from mops.service import (
    _get_exe_path,
    _run_cmd,
    _save_config,
    _load_config,
    install,
    uninstall,
    start,
    stop,
    status,
)


class TestGetExePath:
    def test_frozen(self):
        with patch("sys.frozen", True, create=True), \
             patch("sys.executable", "/path/to/mops.exe"):
            result = _get_exe_path()
            assert result == "/path/to/mops.exe" or "python" in result

    def test_not_frozen(self):
        with patch("sys.frozen", False, create=True):
            result = _get_exe_path()
            assert "python" in result or "mops" in result


class TestRunCmd:
    def test_success(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "ok"
        mock_result.stderr = ""

        with patch("subprocess.run", return_value=mock_result):
            result = _run_cmd(["echo", "test"])
            assert result.returncode == 0

    def test_failure_with_check(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"

        with patch("subprocess.run", return_value=mock_result):
            with pytest.raises(RuntimeError, match="Command failed"):
                _run_cmd(["bad", "command"], check=True)

    def test_failure_without_check(self):
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error"

        with patch("subprocess.run", return_value=mock_result):
            result = _run_cmd(["bad", "command"], check=False)
            assert result.returncode == 1


class TestConfig:
    def test_save_and_load(self, tmp_path):
        config_file = tmp_path / "config.json"
        with patch("mops.service._CONFIG_FILE", config_file), \
             patch("mops.service._CONFIG_DIR", tmp_path):
            _save_config(mode="server", server_port=20080, client_port=20090,
                         api_port=20100, strategy="hash")
            cfg = _load_config()
            assert cfg["mode"] == "server"
            assert cfg["server_port"] == 20080
            assert cfg["client_port"] == 20090
            assert cfg["api_port"] == 20100
            assert cfg["strategy"] == "hash"

    def test_load_defaults(self, tmp_path):
        config_file = tmp_path / "nonexistent.json"
        with patch("mops.service._CONFIG_FILE", config_file):
            cfg = _load_config()
            assert cfg["mode"] == "both"
            assert cfg["server_port"] == 10080
            assert cfg["client_port"] == 10081
            assert cfg["api_port"] == 10082
            assert cfg["strategy"] == "random"


class TestInstall:
    def test_install_linux(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "linux"), \
             patch("subprocess.run", return_value=mock_result) as mock_run, \
             patch("mops.service._get_exe_path", return_value="python -m mops"), \
             patch("mops.service._SERVICE_DIR") as mock_dir, \
             patch("pathlib.Path.write_text") as mock_write, \
             patch("pathlib.Path.exists", return_value=False):
            install()

            calls = mock_run.call_args_list
            assert any("daemon-reload" in str(c) for c in calls)
            assert any("enable" in str(c) for c in calls)

    def test_install_windows(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "win32"), \
             patch("subprocess.run", return_value=mock_result) as mock_run, \
             patch("mops.service._get_exe_path", return_value="C:\\mops.exe"):
            install()

            calls = mock_run.call_args_list
            assert any("sc" in str(c) for c in calls)
            assert any("create" in str(c) for c in calls)


class TestUninstall:
    def test_uninstall_linux(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "linux"), \
             patch("subprocess.run", return_value=mock_result) as mock_run, \
             patch("pathlib.Path.exists", return_value=True), \
             patch("pathlib.Path.unlink"):
            uninstall()
            calls = mock_run.call_args_list
            assert any("stop" in str(c) for c in calls)
            assert any("disable" in str(c) for c in calls)

    def test_uninstall_windows(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "win32"), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            uninstall()
            calls = mock_run.call_args_list
            assert any("delete" in str(c) for c in calls)


class TestStartStop:
    def test_start_linux(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "linux"), \
             patch("mops.service._save_config") as mock_save, \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            start(mode="both", server_port=10080, client_port=10081, api_port=10082, strategy="random")
            mock_save.assert_called_once()
            calls = mock_run.call_args_list
            assert any("start" in str(c) for c in calls)

    def test_start_windows(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "win32"), \
             patch("mops.service._save_config") as mock_save, \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            start(mode="server", server_port=20080, client_port=20090, api_port=20100, strategy="hash")
            mock_save.assert_called_once()
            calls = mock_run.call_args_list
            assert any("sc" in str(c) for c in calls)

    def test_stop_linux(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "linux"), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            stop()
            calls = mock_run.call_args_list
            assert any("stop" in str(c) for c in calls)


class TestStatus:
    def test_status_linux_running(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "active"

        with patch("sys.platform", "linux"), \
             patch("subprocess.run", return_value=mock_result):
            result = status()
            assert result["running"] is True

    def test_status_linux_stopped(self):
        mock_result = MagicMock()
        mock_result.returncode = 3
        mock_result.stdout = "inactive"

        with patch("sys.platform", "linux"), \
             patch("subprocess.run", return_value=mock_result):
            result = status()
            assert result["running"] is False

    def test_status_windows_running(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "SERVICE_NAME: MOPS\n        STATE              : 4                  RUNNING"

        with patch("sys.platform", "win32"), \
             patch("subprocess.run", return_value=mock_result):
            result = status()
            assert result["running"] is True

    def test_status_windows_stopped(self):
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "SERVICE_NAME: MOPS\n        STATE              : 1                  STOPPED"

        with patch("sys.platform", "win32"), \
             patch("subprocess.run", return_value=mock_result):
            result = status()
            assert result["running"] is False


class TestWindowsConfigPathQuoting:
    """Test that Windows service install quotes config paths with spaces."""

    def test_config_path_is_quoted(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "win32"), \
             patch("subprocess.run", return_value=mock_result) as mock_run, \
             patch("mops.service._get_exe_path", return_value="C:\\mops.exe"), \
             patch("mops.service._CONFIG_FILE", Path("C:\\Users\\John Doe\\.config\\mops\\config.json")):
            install()

            # Find the sc create command
            sc_calls = [c for c in mock_run.call_args_list if "sc" in str(c) and "create" in str(c)]
            assert len(sc_calls) == 1
            # The binPath should have the config path quoted
            cmd_args = sc_calls[0][0][0]
            # Check the actual command string (index 3 contains binPath=)
            bin_path_arg = cmd_args[3]
            # Config path should be quoted with double quotes
            assert 'run -c "C:\\Users\\John Doe\\.config\\mops\\config.json"' in bin_path_arg
