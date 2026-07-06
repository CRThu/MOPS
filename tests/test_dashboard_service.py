"""Tests for standalone Dashboard service (dashboard.py)."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from mops.dashboard import MopsDashboard
from mops.scheduler import NodeInfo, Scheduler
from mops.stats import NodeRegistry, TrafficHistory


class TestMopsDashboard:
    def setup_method(self):
        self.dashboard = MopsDashboard(port=0)

    def test_build_status_empty(self):
        status = self.dashboard._build_status()
        assert status["nodes"] == []
        assert status["connections"] == []
        assert status["total_up"] == 0
        assert status["total_down"] == 0
        assert status["mode"] == "dashboard"
        assert status["strategy"] == "mDNS"

    def test_build_status_with_active_node(self):
        info = NodeInfo(
            ip="192.168.1.1", port=10080, api_port=10082,
            hostname="server-a", fails=0,
        )
        self.dashboard._scheduler.add_node(info)
        self.dashboard._cache["192.168.1.1:10080"] = {
            "total_up": 1000,
            "total_down": 2000,
            "active_conns": 5,
            "connections": [{"conn_id": "1", "client_ip": "10.0.0.1"}],
        }

        status = self.dashboard._build_status()
        assert len(status["nodes"]) == 1
        node = status["nodes"][0]
        assert node["ip"] == "192.168.1.1"
        assert node["hostname"] == "server-a"
        assert node["status"] == "active"
        assert node["total_up"] == 1000
        assert node["total_down"] == 2000
        assert node["active_conns"] == 5
        assert len(status["connections"]) == 1
        assert status["connections"][0]["server_node"] == "192.168.1.1:10080"

    def test_build_status_circuit_open(self):
        info = NodeInfo(
            ip="192.168.1.1", port=10080, api_port=10082,
            hostname="server-a", fails=2,
        )
        self.dashboard._scheduler.add_node(info)
        status = self.dashboard._build_status()
        assert status["nodes"][0]["status"] == "circuit-open"

    def test_build_status_with_offline_node(self):
        # Add to registry only (not scheduler)
        self.dashboard._registry.record_seen(
            "192.168.1.2", 10080, 10082, "server-b"
        )
        self.dashboard._registry.mark_offline("192.168.1.2", 10080)

        status = self.dashboard._build_status()
        assert len(status["nodes"]) == 1
        node = status["nodes"][0]
        assert node["status"] == "offline"
        assert node["hostname"] == "server-b"

    def test_build_status_aggregates_totals(self):
        info1 = NodeInfo(ip="10.0.0.1", port=10080, api_port=10082, hostname="a")
        info2 = NodeInfo(ip="10.0.0.2", port=10080, api_port=10082, hostname="b")
        self.dashboard._scheduler.add_node(info1)
        self.dashboard._scheduler.add_node(info2)
        self.dashboard._cache["10.0.0.1:10080"] = {"total_up": 100, "total_down": 200, "active_conns": 1}
        self.dashboard._cache["10.0.0.2:10080"] = {"total_up": 300, "total_down": 400, "active_conns": 2}

        status = self.dashboard._build_status()
        assert status["total_up"] == 400
        assert status["total_down"] == 600
        assert status["active_conns"] == 3

    @pytest.mark.asyncio
    async def test_handle_status_endpoint(self):
        app = web.Application()
        app.router.add_get("/api/dashboard", self.dashboard._handle_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/dashboard")
            assert resp.status == 200
            data = await resp.json()
            assert data["mode"] == "dashboard"

    @pytest.mark.asyncio
    async def test_handle_dashboard_endpoint(self):
        app = web.Application()
        app.router.add_get("/", self.dashboard._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            assert resp.status == 200

    @pytest.mark.asyncio
    async def test_poll_loop_once(self):
        """Test that _poll_loop records a snapshot even with no nodes."""
        self.dashboard._history = TrafficHistory(capacity=5)
        # Just call once and verify no crash
        self.dashboard._scheduler = Scheduler()
        await self.dashboard._poll_loop_iteration()

    def test_speed_computed(self):
        # Pre-record history
        self.dashboard._history.record(1000, 2000, 3)
        time.sleep(0.05)
        self.dashboard._history.record(1500, 3000, 4)
        status = self.dashboard._build_status()
        assert status["speed_up"] > 0
        assert status["speed_down"] > 0

    @pytest.mark.asyncio
    async def test_stop_with_discovery_and_runner(self):
        self.dashboard._discovery = MagicMock()
        self.dashboard._runner = AsyncMock()
        await self.dashboard.stop()
        self.dashboard._discovery.stop.assert_called_once()
        self.dashboard._runner.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_without_resources(self):
        self.dashboard._discovery = None
        self.dashboard._runner = None
        await self.dashboard.stop()

    @pytest.mark.asyncio
    async def test_query_success(self):
        node = NodeInfo(ip="192.168.1.1", port=10080, api_port=10082)
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value={
            "total_up": 500, "total_down": 1000, "active_conns": 3,
        })
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=False)

        mock_session = AsyncMock()
        mock_session.get = MagicMock(return_value=mock_response)
        mock_session.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session.__aexit__ = AsyncMock(return_value=False)

        with patch("mops.dashboard.aiohttp.ClientSession", return_value=mock_session):
            await self.dashboard._query(node)

        assert "192.168.1.1:10080" in self.dashboard._cache
        assert self.dashboard._cache["192.168.1.1:10080"]["total_up"] == 500

    @pytest.mark.asyncio
    async def test_query_failure_keeps_stale(self):
        node = NodeInfo(ip="192.168.1.1", port=10080, api_port=10082)
        self.dashboard._cache["192.168.1.1:10080"] = {"total_up": 100}

        with patch("mops.dashboard.aiohttp.ClientSession", side_effect=ConnectionError("refused")):
            await self.dashboard._query(node)

        assert self.dashboard._cache["192.168.1.1:10080"]["total_up"] == 100

    @pytest.mark.asyncio
    async def test_poll_iteration_with_nodes(self):
        self.dashboard._scheduler.add_node(
            NodeInfo(ip="10.0.0.1", port=10080, api_port=10082)
        )
        self.dashboard._cache["10.0.0.1:10080"] = {
            "total_up": 100, "total_down": 200, "active_conns": 5,
        }
        with patch.object(self.dashboard, "_query", new_callable=AsyncMock):
            await self.dashboard._poll_loop_iteration()
        assert len(self.dashboard._history._samples) == 1

    @pytest.mark.asyncio
    async def test_handle_dashboard_fallback(self):
        app = web.Application()
        app.router.add_get("/", self.dashboard._handle_dashboard)
        with patch("mops.dashboard._STATIC_DIR") as mock_dir:
            mock_dir.__truediv__ = MagicMock(return_value=MagicMock(exists=MagicMock(return_value=False)))
            async with TestClient(TestServer(app)) as client:
                resp = await client.get("/")
                assert resp.status == 200
                text = await resp.text()
                assert "MOPS Dashboard" in text

    @pytest.mark.asyncio
    async def test_poll_loop_iteration_with_connections(self):
        self.dashboard._scheduler.add_node(
            NodeInfo(ip="10.0.0.1", port=10080, api_port=10082)
        )
        self.dashboard._cache["10.0.0.1:10080"] = {
            "total_up": 100, "total_down": 200, "active_conns": 5,
            "connections": [{"conn_id": "1"}],
        }
        with patch.object(self.dashboard, "_query", new_callable=AsyncMock):
            await self.dashboard._poll_loop_iteration()
        status = self.dashboard._build_status()
        assert len(status["connections"]) == 1
