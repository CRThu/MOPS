"""Tests for mDNS service discovery (discovery.py)."""

from unittest.mock import MagicMock, AsyncMock, patch

import pytest

from mops.discovery import NodeDiscovery
from mops.scheduler import NodeInfo, Scheduler


class TestNodeDiscovery:
    def setup_method(self):
        self.scheduler = Scheduler()
        self.discovery = NodeDiscovery(self.scheduler)

    def test_add_service(self):
        zc = MagicMock()
        info = MagicMock()
        info.name = "mops-server-1-10080._mops-proxy._tcp.local."
        info.port = 10080
        info.properties = {b"weight": b"2"}
        info.parsed_addresses.return_value = ["192.168.1.100"]

        zc.get_service_info.return_value = info
        self.discovery.add_service(zc, "_mops-proxy._tcp.local.", info.name)

        nodes = self.scheduler.get_all_nodes()
        assert len(nodes) == 1
        assert nodes[0].ip == "192.168.1.100"
        assert nodes[0].port == 10080
        assert nodes[0].weight == 2

    def test_add_service_no_info(self):
        zc = MagicMock()
        zc.get_service_info.return_value = None

        self.discovery.add_service(zc, "_mops-proxy._tcp.local.", "test._mops-proxy._tcp.local.")
        assert len(self.scheduler.get_all_nodes()) == 0

    def test_add_service_no_weight(self):
        zc = MagicMock()
        info = MagicMock()
        info.name = "mops-server-1-10080._mops-proxy._tcp.local."
        info.port = 10080
        info.properties = {}
        info.parsed_addresses.return_value = ["192.168.1.100"]

        zc.get_service_info.return_value = info
        self.discovery.add_service(zc, "_mops-proxy._tcp.local.", info.name)

        nodes = self.scheduler.get_all_nodes()
        assert len(nodes) == 1
        assert nodes[0].weight == 1  # default

    def test_remove_service(self):
        # First add a node
        zc = MagicMock()
        info = MagicMock()
        info.name = "mops-server-1-10080._mops-proxy._tcp.local."
        info.port = 10080
        info.properties = {b"weight": b"1"}
        info.parsed_addresses.return_value = ["192.168.1.100"]

        zc.get_service_info.return_value = info
        self.discovery.add_service(zc, "_mops-proxy._tcp.local.", info.name)
        assert len(self.scheduler.get_all_nodes()) == 1

        # Now remove it
        self.discovery.remove_service(zc, "_mops-proxy._tcp.local.", info.name)
        assert len(self.scheduler.get_all_nodes()) == 0

    def test_remove_service_no_info(self):
        zc = MagicMock()
        zc.get_service_info.return_value = None

        # Should not crash
        self.discovery.remove_service(zc, "_mops-proxy._tcp.local.", "test._mops-proxy._tcp.local.")

    def test_update_service(self):
        zc = MagicMock()
        info = MagicMock()
        info.name = "mops-server-1-10080._mops-proxy._tcp.local."
        info.port = 10080
        info.properties = {b"weight": b"1"}
        info.parsed_addresses.return_value = ["192.168.1.100"]

        zc.get_service_info.return_value = info
        self.discovery.update_service(zc, "_mops-proxy._tcp.local.", info.name)

        nodes = self.scheduler.get_all_nodes()
        assert len(nodes) == 1

    def test_extract_ip_unknown(self):
        info = MagicMock()
        info.parsed_addresses.return_value = []
        ip = self.discovery._extract_ip(info)
        assert ip == "unknown"

    def test_start_stop(self):
        with patch("mops.discovery.Zeroconf") as mock_zc_cls, \
             patch("mops.discovery.ServiceBrowser") as mock_browser_cls:
            mock_zc = MagicMock()
            mock_zc_cls.return_value = mock_zc
            mock_browser = MagicMock()
            mock_browser_cls.return_value = mock_browser

            self.discovery.start()
            assert self.discovery._zc == mock_zc
            assert self.discovery._browser == mock_browser

            self.discovery.stop()
            mock_browser.cancel.assert_called_once()
            mock_zc.close.assert_called_once()

    def test_stop_without_start(self):
        # Should not crash
        self.discovery.stop()

    def test_start_error_handling(self):
        """Zeroconf init failure should not crash, just log."""
        with patch("mops.discovery.Zeroconf", side_effect=OSError("no network")):
            # Should not raise
            self.discovery.start()
            # _zc should remain None since init failed
            assert self.discovery._zc is None
