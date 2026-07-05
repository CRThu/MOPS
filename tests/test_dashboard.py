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
        api = MopsApi(port=0, server_stats=stats, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            html = await resp.text()
            assert "MOPS" in html
            assert "text/html" in resp.content_type

    @pytest.mark.asyncio
    async def test_dashboard_has_vis_network(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "cytoscape" in html
            assert "cytoscape.min.js" in html

    @pytest.mark.asyncio
    async def test_dashboard_has_dynamic_topology(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "buildTopo" in html
            assert "cytoscape" in html

    @pytest.mark.asyncio
    async def test_dashboard_has_auto_refresh_js(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "setInterval" in html
            assert "/api/server" in html
            assert "/api/client" in html

    @pytest.mark.asyncio
    async def test_dashboard_shows_ports(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, client_stats=stats,
                      mode="both", server_port=10080, client_port=10081)

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "10080" in html
            assert "10081" in html

    @pytest.mark.asyncio
    async def test_dashboard_uses_tailwind(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "tailwindcss" in html
            assert "bg-card" in html

    @pytest.mark.asyncio
    async def test_dashboard_has_stats_bar(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "grid-cols-6" in html
            assert "Server" in html
            assert "Client" in html

    @pytest.mark.asyncio
    async def test_dashboard_has_node_list(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "Discovered Nodes" in html
            assert "nodes-list" in html

    @pytest.mark.asyncio
    async def test_dashboard_loads_from_file(self):
        from mops.api import _DASHBOARD_HTML_PATH
        assert _DASHBOARD_HTML_PATH.exists()
        assert _DASHBOARD_HTML_PATH.suffix == ".html"
