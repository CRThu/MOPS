"""Tests for Web Dashboard HTML rendering."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from mops.api import MopsApi
from mops.stats import TrafficStats


class TestDashboardHTML:
    @pytest.mark.asyncio
    async def test_dashboard_contains_title(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            html = await resp.text()
            assert "MOPS" in html
            assert "text/html" in resp.content_type

    @pytest.mark.asyncio
    async def test_dashboard_has_topology_container(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "topo-container" in html

    @pytest.mark.asyncio
    async def test_dashboard_has_connections_panel(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "conn-list" in html
            assert "Connections" in html

    @pytest.mark.asyncio
    async def test_dashboard_has_stats_bar(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "stats-bar" in html
            assert "Server" in html

    @pytest.mark.asyncio
    async def test_dashboard_loads_from_file(self):
        from mops.api import _DASHBOARD_HTML_PATH
        assert _DASHBOARD_HTML_PATH.exists()
        assert _DASHBOARD_HTML_PATH.suffix == ".html"
