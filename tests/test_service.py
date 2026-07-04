"""Tests for system service management (service.py)."""

from unittest.mock import MagicMock, patch, AsyncMock
import subprocess

import pytest

from mops.service import (
    _get_exe_path,
    _run_cmd,
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
            # Reset module to pick up the patched values
            result = _get_exe_path()
            # When frozen, returns sys.executable
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
            install("both", 10080, "random")

            # Should call daemon-reload and enable
            calls = mock_run.call_args_list
            assert any("daemon-reload" in str(c) for c in calls)
            assert any("enable" in str(c) for c in calls)

    def test_install_windows(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "win32"), \
             patch("subprocess.run", return_value=mock_result) as mock_run, \
             patch("mops.service._get_exe_path", return_value="C:\\mops.exe"):
            install("server", 20080, "hash")

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
             patch("subprocess.run", return_value=mock_result) as mock_run:
            start()
            calls = mock_run.call_args_list
            assert any("start" in str(c) for c in calls)

    def test_stop_linux(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "linux"), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            stop()
            calls = mock_run.call_args_list
            assert any("stop" in str(c) for c in calls)

    def test_start_windows(self):
        mock_result = MagicMock()
        mock_result.returncode = 0

        with patch("sys.platform", "win32"), \
             patch("subprocess.run", return_value=mock_result) as mock_run:
            start()
            calls = mock_run.call_args_list
            assert any("sc" in str(c) for c in calls)


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
