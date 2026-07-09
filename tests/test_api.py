"""Tests for REST API (api.py)."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from mops.api import MopsApi
from mops.stats import ConnectionTracker, TrafficStats


class TestMopsApi:
    @pytest.mark.asyncio
    async def test_api_server_status(self):
        stats = TrafficStats()
        stats.record_upload("server:10080", 1000)
        stats.record_download("server:10080", 2000)
        stats.active_conns = 3

        api = MopsApi(port=0, server_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/api/server", api._handle_server_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/server")
            assert resp.status == 200
            data = await resp.json()
            assert data["total_up"] == 1000
            assert data["total_down"] == 2000
            assert data["active_conns"] == 3
            assert len(data["nodes"]) == 1
            assert "connections" in data

    @pytest.mark.asyncio
    async def test_api_server_with_connections(self):
        stats = TrafficStats()
        tracker = ConnectionTracker()
        cid = tracker.start("192.168.1.5", "example.com", 443)
        tracker.end(cid)

        api = MopsApi(port=0, server_stats=stats, mode="both", conn_tracker=tracker)

        app = web.Application()
        app.router.add_get("/api/server", api._handle_server_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/server")
            assert resp.status == 200
            data = await resp.json()
            assert len(data["connections"]) == 1
            conn = data["connections"][0]
            assert conn["client_ip"] == "192.168.1.5"
            assert conn["target_host"] == "example.com"
            assert conn["status"] == "completed"

    @pytest.mark.asyncio
    async def test_api_server_no_stats(self):
        api = MopsApi(port=0, mode="client")

        app = web.Application()
        app.router.add_get("/api/server", api._handle_server_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/server")
            assert resp.status == 200
            data = await resp.json()
            assert data["mode"] == "client"
            assert data["nodes"] == []

    @pytest.mark.asyncio
    async def test_api_empty_nodes(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, mode="server")

        app = web.Application()
        app.router.add_get("/api/server", api._handle_server_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/server")
            assert resp.status == 200
            data = await resp.json()
            assert data["nodes"] == []
            assert data["total_up"] == 0
            assert data["total_down"] == 0
            assert data["connections"] == []

    @pytest.mark.asyncio
    async def test_api_unified_schema_fields(self):
        """Verify /api/dashboard returns all required fields for the frontend."""
        stats = TrafficStats()
        stats.record_upload("server:10080", 500)
        stats.record_download("server:10080", 1000)

        api = MopsApi(port=10082, server_stats=stats, mode="both", strategy="random")

        app = web.Application()
        app.router.add_get("/api/dashboard", api._handle_server_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/dashboard")
            assert resp.status == 200
            data = await resp.json()

            # Top-level fields
            assert "nodes" in data
            assert "connections" in data
            assert "total_up" in data
            assert "total_down" in data
            assert "speed_up" in data
            assert "speed_down" in data
            assert "active_conns" in data
            assert "uptime" in data
            assert "mode" in data
            assert "strategy" in data
            assert "local_client" in data

            assert data["mode"] == "both"
            assert data["strategy"] == "random"
            assert data["total_up"] == 500
            assert data["total_down"] == 1000
            assert data["local_client"] is None

            # Node schema
            assert len(data["nodes"]) >= 1
            node = data["nodes"][0]
            assert "ip" in node
            assert "port" in node
            assert "api_port" in node
            assert "hostname" in node
            assert "fails" in node
            assert "status" in node
            assert "total_up" in node
            assert "total_down" in node
            assert "active_conns" in node
            assert "connections" in node
            assert "speed_up" in node
            assert "speed_down" in node

    @pytest.mark.asyncio
    async def test_api_with_client_stats(self):
        """Verify local_client is set when client_stats provided."""
        server_stats = TrafficStats()
        server_stats.record_upload("server:10080", 100)
        client_stats = TrafficStats()
        client_stats.record_upload("192.168.1.100:10080", 200)

        api = MopsApi(
            port=10082,
            server_stats=server_stats,
            client_stats=client_stats,
            mode="both",
            client_listen="127.0.0.1",
            client_port=10081,
        )

        app = web.Application()
        app.router.add_get("/api/dashboard", api._handle_server_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/dashboard")
            data = await resp.json()

            assert data["local_client"] == {"ip": "127.0.0.1", "port": 10081}
            assert data["total_up"] == 300  # server + client
            assert len(data["nodes"]) == 2  # server node + client node
