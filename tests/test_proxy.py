"""Tests for proxy.py (system proxy configuration)."""

import os
from unittest.mock import MagicMock, mock_open, patch

import pytest

from mops.proxy import (
    _get_proxy_url,
    _get_active_network_services,
    _linux_proxy_off,
    _linux_proxy_on,
    _linux_proxy_status,
    _macos_proxy_off,
    _macos_proxy_on,
    _macos_proxy_status,
    _win_reg_get,
    _win_reg_set,
    _windows_proxy_off,
    _windows_proxy_on,
    _windows_proxy_status,
    proxy_off,
    proxy_on,
    proxy_status,
)


class TestGetProxyUrl:
    def test_format(self):
        assert _get_proxy_url(10081) == "127.0.0.1:10081"

    def test_custom_port(self):
        assert _get_proxy_url(8080) == "127.0.0.1:8080"


class TestWindowsProxy:
    @patch("mops.proxy._notify_windows")
    @patch("mops.proxy._win_reg_set")
    def test_windows_proxy_on(self, mock_set, mock_notify):
        _windows_proxy_on(10081)
        assert mock_set.call_count == 3
        mock_set.assert_any_call("ProxyEnable", 1)
        mock_set.assert_any_call("ProxyServer", "127.0.0.1:10081")
        mock_notify.assert_called_once()

    @patch("mops.proxy._notify_windows")
    @patch("mops.proxy._win_reg_set")
    def test_windows_proxy_off(self, mock_set, mock_notify):
        _windows_proxy_off()
        mock_set.assert_called_once_with("ProxyEnable", 0)
        mock_notify.assert_called_once()

    @patch("mops.proxy._win_reg_get")
    def test_windows_proxy_status_enabled(self, mock_get):
        mock_get.side_effect = lambda name: {"ProxyEnable": 1, "ProxyServer": "127.0.0.1:10081"}[name]
        result = _windows_proxy_status()
        assert result["enabled"] is True
        assert result["server"] == "127.0.0.1:10081"

    @patch("mops.proxy._win_reg_get")
    def test_windows_proxy_status_disabled(self, mock_get):
        mock_get.return_value = None
        result = _windows_proxy_status()
        assert result["enabled"] is False
        assert result["server"] == ""

    @patch("mops.proxy.winreg")
    def test_win_reg_set_dword(self, mock_winreg):
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.REG_DWORD = 4
        mock_winreg.KEY_SET_VALUE = 1
        _win_reg_set("ProxyEnable", 1)
        mock_winreg.SetValueEx.assert_called_once()

    @patch("mops.proxy.winreg")
    def test_win_reg_get_found(self, mock_winreg):
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.KEY_READ = 0
        mock_winreg.QueryValueEx.return_value = ("127.0.0.1:10081", None)
        result = _win_reg_get("ProxyServer")
        assert result == "127.0.0.1:10081"

    @patch("mops.proxy.winreg")
    def test_win_reg_get_not_found(self, mock_winreg):
        mock_winreg.OpenKey.side_effect = FileNotFoundError
        result = _win_reg_get("ProxyServer")
        assert result is None


class TestLinuxProxy:
    @patch("builtins.open", new_callable=mock_open)
    @patch("mops.proxy.logger")
    def test_linux_proxy_on(self, mock_logger, mock_file):
        _linux_proxy_on(10081)
        mock_file.assert_called_once()
        written = mock_file().write.call_args[0][0]
        assert "http://127.0.0.1:10081" in written

    @patch("os.remove")
    @patch("os.path.exists", return_value=True)
    @patch("mops.proxy.logger")
    def test_linux_proxy_off_exists(self, mock_logger, mock_exists, mock_remove):
        _linux_proxy_off()
        mock_remove.assert_called_once()

    @patch("os.path.exists", return_value=False)
    @patch("mops.proxy.logger")
    def test_linux_proxy_off_not_exists(self, mock_logger, mock_exists):
        _linux_proxy_off()

    @patch("os.path.exists", return_value=True)
    def test_linux_proxy_status_enabled(self, mock_exists):
        result = _linux_proxy_status()
        assert result["enabled"] is True

    @patch("os.path.exists", return_value=False)
    @patch.dict(os.environ, {}, clear=True)
    def test_linux_proxy_status_disabled(self, mock_exists):
        result = _linux_proxy_status()
        assert result["enabled"] is False
        assert result["platform"] == "linux"


class TestMacOSProxy:
    @patch("mops.proxy.subprocess.run")
    @patch("mops.proxy._get_active_network_services", return_value=["Wi-Fi", "Ethernet"])
    def test_macos_proxy_on(self, mock_services, mock_run):
        _macos_proxy_on(10081)
        assert mock_run.call_count == 4

    @patch("mops.proxy.subprocess.run")
    @patch("mops.proxy._get_active_network_services", return_value=["Wi-Fi"])
    def test_macos_proxy_off(self, mock_services, mock_run):
        _macos_proxy_off()
        assert mock_run.call_count == 2

    @patch("mops.proxy.subprocess.run")
    @patch("mops.proxy._get_active_network_services", return_value=["Wi-Fi"])
    def test_macos_proxy_status_enabled(self, mock_services, mock_run):
        mock_run.return_value = MagicMock(
            stdout="Enabled: Yes\nServer: 127.0.0.1\nPort: 10081\n"
        )
        result = _macos_proxy_status()
        assert result["enabled"] is True
        assert result["server"] == "127.0.0.1"

    @patch("mops.proxy.subprocess.run")
    @patch("mops.proxy._get_active_network_services", return_value=[])
    def test_macos_proxy_status_no_services(self, mock_services, mock_run):
        result = _macos_proxy_status()
        assert result["enabled"] is False
        assert result["server"] == ""

    @patch("mops.proxy.subprocess.run")
    def test_get_active_network_services(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="An asterisk (*) denotes something ...\nWi-Fi\nEthernet\n"
        )
        result = _get_active_network_services()
        assert result == ["Wi-Fi", "Ethernet"]

    @patch("mops.proxy.subprocess.run")
    def test_get_active_network_services_with_star(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="*\nWi-Fi\n*Ethernet\n"
        )
        result = _get_active_network_services()
        assert result == ["Wi-Fi"]


class TestPlatformDispatch:
    @patch("mops.proxy.platform.system", return_value="Windows")
    @patch("mops.proxy._windows_proxy_on")
    def test_proxy_on_windows(self, mock_win_on, mock_platform):
        proxy_on(10081)
        mock_win_on.assert_called_once_with(10081)

    @patch("mops.proxy.platform.system", return_value="Linux")
    @patch("mops.proxy._linux_proxy_on")
    def test_proxy_on_linux(self, mock_linux_on, mock_platform):
        proxy_on(10081)
        mock_linux_on.assert_called_once_with(10081)

    @patch("mops.proxy.platform.system", return_value="Darwin")
    @patch("mops.proxy._macos_proxy_on")
    def test_proxy_on_darwin(self, mock_mac_on, mock_platform):
        proxy_on(10081)
        mock_mac_on.assert_called_once_with(10081)

    @patch("mops.proxy.platform.system", return_value="Windows")
    @patch("mops.proxy._windows_proxy_off")
    def test_proxy_off_windows(self, mock_win_off, mock_platform):
        proxy_off()
        mock_win_off.assert_called_once()

    @patch("mops.proxy.platform.system", return_value="Linux")
    @patch("mops.proxy._linux_proxy_off")
    def test_proxy_off_linux(self, mock_linux_off, mock_platform):
        proxy_off()
        mock_linux_off.assert_called_once()

    @patch("mops.proxy.platform.system", return_value="Darwin")
    @patch("mops.proxy._macos_proxy_off")
    def test_proxy_off_darwin(self, mock_mac_off, mock_platform):
        proxy_off()
        mock_mac_off.assert_called_once()

    @patch("mops.proxy.platform.system", return_value="Windows")
    @patch("mops.proxy._windows_proxy_status")
    def test_proxy_status_windows(self, mock_win_status, mock_platform):
        proxy_status()
        mock_win_status.assert_called_once()

    @patch("mops.proxy.platform.system", return_value="Linux")
    @patch("mops.proxy._linux_proxy_status")
    def test_proxy_status_linux(self, mock_linux_status, mock_platform):
        proxy_status()
        mock_linux_status.assert_called_once()

    @patch("mops.proxy.platform.system", return_value="Darwin")
    @patch("mops.proxy._macos_proxy_status")
    def test_proxy_status_darwin(self, mock_mac_status, mock_platform):
        proxy_status()
        mock_mac_status.assert_called_once()
