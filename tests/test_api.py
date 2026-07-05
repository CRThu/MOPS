"""Tests for REST API (api.py)."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from mops.api import MopsApi
from mops.stats import TrafficStats


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

    @pytest.mark.asyncio
    async def test_api_client_status(self):
        stats = TrafficStats()
        stats.record_upload("10.0.0.1:10080", 500)
        stats.record_download("10.0.0.1:10080", 800)

        api = MopsApi(port=0, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/api/client", api._handle_client_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/client")
            assert resp.status == 200
            data = await resp.json()
            assert data["total_up"] == 500
            assert data["total_down"] == 800
            assert len(data["nodes"]) == 1

    @pytest.mark.asyncio
    async def test_api_server_no_stats(self):
        api = MopsApi(port=0, mode="server")

        app = web.Application()
        app.router.add_get("/api/server", api._handle_server_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/server")
            assert resp.status == 503

    @pytest.mark.asyncio
    async def test_api_client_no_stats(self):
        api = MopsApi(port=0, mode="client")

        app = web.Application()
        app.router.add_get("/api/client", api._handle_client_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/client")
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
