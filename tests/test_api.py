"""Tests for REST API (api.py)."""

import json
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import AioHTTPTestCase, TestClient, TestServer

from mops.api import MopsApi
from mops.stats import TrafficStats


class TestMopsApi:
    """Test API endpoints."""

    @pytest.mark.asyncio
    async def test_get_status(self):
        stats = TrafficStats()
        stats.record_upload("10.0.0.1:10080", 1000)
        stats.record_download("10.0.0.1:10080", 2000)
        stats.active_conns = 3

        api = MopsApi(
            port=10082,
            stats=stats,
            mode="both",
            strategy="random",
        )

        # Create aiohttp test app
        app = web.Application()
        app.router.add_get("/status", api._handle_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/status")
            assert resp.status == 200
            data = await resp.json()

            assert data["mode"] == "both"
            assert data["strategy"] == "random"
            assert data["total_up"] == 1000
            assert data["total_down"] == 2000
            assert data["active_conns"] == 3
            assert len(data["nodes"]) == 1
            assert data["nodes"][0]["ip"] == "10.0.0.1"
            assert data["nodes"][0]["up"] == 1000
            assert data["nodes"][0]["down"] == 2000

    @pytest.mark.asyncio
    async def test_get_status_no_stats(self):
        api = MopsApi(port=10082, stats=None)

        app = web.Application()
        app.router.add_get("/status", api._handle_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/status")
            assert resp.status == 503

    @pytest.mark.asyncio
    async def test_get_status_empty_nodes(self):
        stats = TrafficStats()
        api = MopsApi(
            port=10082,
            stats=stats,
            mode="server",
            strategy="hash",
        )

        app = web.Application()
        app.router.add_get("/status", api._handle_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/status")
            assert resp.status == 200
            data = await resp.json()
            assert data["nodes"] == []
            assert data["total_up"] == 0
            assert data["total_down"] == 0
