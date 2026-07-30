"""RESTful API for MOPS status and Web Dashboard (aiohttp)."""

from __future__ import annotations

import socket
import time
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

from .web import serve_index, setup_static_routes

if TYPE_CHECKING:
    from .stats import ConnectionTracker, TrafficHistory, TrafficStats


class MopsApi:
    """HTTP API server with Dashboard and status endpoints."""

    def __init__(
        self,
        port: int,
        host: str = "0.0.0.0",
        server_stats: TrafficStats | None = None,
        client_stats: TrafficStats | None = None,
        conn_tracker: ConnectionTracker | None = None,
        traffic_history: TrafficHistory | None = None,
        mode: str = "both",
        strategy: str = "random",
        client_listen: str = "127.0.0.1",
        client_port: int = 10081,
    ) -> None:
        self.port = port
        self.host = host
        self._server_stats = server_stats
        self._client_stats = client_stats
        self._conn_tracker = conn_tracker
        self._traffic_history = traffic_history
        self._mode = mode
        self._strategy = strategy
        self._client_listen = client_listen
        self._client_port = client_port
        self._runner: web.AppRunner | None = None
        self._start_time = time.monotonic()

    def _snapshot(self) -> dict:
        hostname = socket.gethostname()
        nodes: list[dict] = []
        total_up = 0
        total_down = 0

        # Count active connections per server from conn_tracker
        active_by_server: dict[str, int] = {}
        if self._conn_tracker:
            for conn in self._conn_tracker.get_connections():
                if conn["status"] == "active":
                    key = f"{conn['target_host']}:{conn['target_port']}"
                    active_by_server[key] = active_by_server.get(key, 0) + 1

        # Server-side traffic (this node's own connections)
        if self._server_stats:
            for name, ns in self._server_stats.get_all_nodes().items():
                node = {
                    "ip": ns.ip,
                    "port": ns.port,
                    "api_port": self.port,
                    "hostname": hostname if ns.ip == "server" else ns.ip,
                    "fails": ns.fails,
                    "status": "active",
                    "total_up": ns.up,
                    "total_down": ns.down,
                    "active_conns": self._conn_tracker.active_count() if self._conn_tracker else (self._server_stats.active_conns if self._server_stats else 0),
                    "connections": [],
                    "speed_up": 0,
                    "speed_down": 0,
                }
                nodes.append(node)
                total_up += ns.up
                total_down += ns.down

        # Client-side traffic (per-server breakdown)
        if self._client_stats:
            for name, ns in self._client_stats.get_all_nodes().items():
                node = {
                    "ip": ns.ip,
                    "port": ns.port,
                    "api_port": 0,
                    "hostname": ns.ip,
                    "fails": ns.fails,
                    "status": "active",
                    "total_up": ns.up,
                    "total_down": ns.down,
                    "active_conns": active_by_server.get(f"{ns.ip}:{ns.port}", 0),
                    "connections": [],
                    "speed_up": 0,
                    "speed_down": 0,
                }
                nodes.append(node)
                total_up += ns.up
                total_down += ns.down

        speed_up, speed_down = (0, 0)
        if self._traffic_history:
            speed_up, speed_down = self._traffic_history.compute_speed()

        active_conns = 0
        if self._conn_tracker:
            active_conns = self._conn_tracker.active_count()
        elif self._server_stats:
            active_conns = self._server_stats.active_conns

        result: dict = {
            "nodes": nodes,
            "connections": [],
            "total_up": total_up,
            "total_down": total_down,
            "speed_up": speed_up,
            "speed_down": speed_down,
            "active_conns": active_conns,
            "uptime": time.monotonic() - self._start_time,
            "mode": self._mode,
            "strategy": self._strategy,
            "local_client": {"ip": self._client_listen, "port": self._client_port} if self._client_stats else None,
        }

        if self._conn_tracker:
            result["connections"] = self._conn_tracker.get_connections()

        return result

    async def _handle_server_status(self, request: web.Request) -> web.Response:
        return web.json_response(self._snapshot())

    async def _handle_dashboard(self, request: web.Request) -> web.Response:
        return await serve_index(request)

    async def run(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._handle_dashboard)
        app.router.add_get("/api/server", self._handle_server_status)
        app.router.add_get("/api/dashboard", self._handle_server_status)
        setup_static_routes(app)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"API server listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            logger.info("API server stopped")
