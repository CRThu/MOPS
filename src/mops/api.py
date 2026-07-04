"""RESTful API for MOPS status (aiohttp)."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from .stats import TrafficStats


class MopsApi:
    """HTTP API server exposing GET /status."""

    def __init__(
        self,
        port: int,
        host: str = "127.0.0.1",
        stats: TrafficStats | None = None,
        mode: str = "both",
        strategy: str = "random",
        server_host: str = "0.0.0.0",
        server_port: int = 10080,
        client_listen: str = "127.0.0.1",
        client_port: int = 10081,
    ) -> None:
        self.port = port
        self.host = host
        self._stats = stats
        self._mode = mode
        self._strategy = strategy
        self._server_host = server_host
        self._server_port = server_port
        self._client_listen = client_listen
        self._client_port = client_port
        self._runner: web.AppRunner | None = None

    async def _handle_status(self, request: web.Request) -> web.Response:
        if not self._stats:
            return web.json_response({"error": "Stats not available"}, status=503)

        snapshot = self._stats.get_snapshot(
            mode=self._mode,
            strategy=self._strategy,
            server_host=self._server_host,
            server_port=self._server_port,
            client_listen=self._client_listen,
            client_port=self._client_port,
            api_port=self.port,
        )

        data = {
            "mode": snapshot.mode,
            "base_port": snapshot.server_port,
            "strategy": snapshot.strategy,
            "uptime": f"{snapshot.uptime:.0f}s",
            "server": {
                "host": snapshot.server_host,
                "port": snapshot.server_port,
            },
            "client": {
                "listen": snapshot.client_listen,
                "port": snapshot.client_port,
            },
            "nodes": snapshot.nodes,
            "total_up": snapshot.total_up,
            "total_down": snapshot.total_down,
            "active_conns": snapshot.active_conns,
        }

        return web.json_response(data)

    async def run(self) -> None:
        app = web.Application()
        app.router.add_get("/status", self._handle_status)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"API server listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            logger.info("API server stopped")
