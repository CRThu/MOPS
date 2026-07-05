"""Additional API tests for run/stop and dashboard."""

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import AsyncMock, patch

from mops.api import MopsApi
from mops.stats import TrafficStats


class TestMopsApiRunStop:
    @pytest.mark.asyncio
    async def test_run_and_stop(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats)

        mock_runner = AsyncMock()
        mock_site = AsyncMock()

        with patch("aiohttp.web.AppRunner", return_value=mock_runner), \
             patch("aiohttp.web.TCPSite", return_value=mock_site):
            await api.run()
            mock_runner.setup.assert_called_once()
            mock_site.start.assert_called_once()

            await api.stop()
            mock_runner.cleanup.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_without_runner(self):
        api = MopsApi(port=10082)
        await api.stop()  # Should not raise


class TestDashboardHTML:
    @pytest.mark.asyncio
    async def test_dashboard_returns_html(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            assert "text/html" in resp.content_type
            html = await resp.text()
            assert "MOPS" in html
            assert "fetch" in html

    @pytest.mark.asyncio
    async def test_dashboard_server_only_mode(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, mode="server")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            html = await resp.text()
            assert "showS=true" in html
            assert "showC=false" in html

    @pytest.mark.asyncio
    async def test_dashboard_client_only_mode(self):
        stats = TrafficStats()
        api = MopsApi(port=0, client_stats=stats, mode="client")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            html = await resp.text()
            assert "showS=false" in html
            assert "showC=true" in html

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
    async def test_dashboard_compact_layout(self):
        stats = TrafficStats()
        api = MopsApi(port=0, server_stats=stats, client_stats=stats, mode="both")

        app = web.Application()
        app.router.add_get("/", api._handle_dashboard)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            html = await resp.text()
            assert "h-screen" in html
            assert "overflow-hidden" in html
