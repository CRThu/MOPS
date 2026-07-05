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
        api = MopsApi(port=0, mode="server")

        app = web.Application()
        app.router.add_get("/api/server", api._handle_server_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/server")
            assert resp.status == 503

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
