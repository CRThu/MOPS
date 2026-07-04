"""Additional API tests for run/stop methods."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web

from mops.api import MopsApi
from mops.stats import TrafficStats


class TestMopsApiRunStop:
    @pytest.mark.asyncio
    async def test_run_and_stop(self):
        stats = TrafficStats()
        api = MopsApi(port=0, stats=stats)  # port=0 for random

        # Mock the aiohttp runner
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
        # Should not raise
        await api.stop()

    @pytest.mark.asyncio
    async def test_handle_status_uptime_format(self):
        stats = TrafficStats()
        api = MopsApi(port=10082, stats=stats, mode="server", strategy="hash")

        app = web.Application()
        app.router.add_get("/status", api._handle_status)

        from aiohttp.test_utils import TestClient, TestServer
        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/status")
            assert resp.status == 200
            data = await resp.json()
            assert "uptime" in data
            assert data["strategy"] == "hash"
