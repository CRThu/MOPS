"""RESTful API for MOPS status and Web Dashboard (aiohttp)."""

from __future__ import annotations

import socket
import time
from pathlib import Path
from typing import TYPE_CHECKING

from aiohttp import web
from loguru import logger

if TYPE_CHECKING:
    from .stats import ConnectionTracker, TrafficHistory, TrafficStats

_STATIC_DIR = Path(__file__).parent / "static"
_DASHBOARD_HTML_PATH = Path(__file__).parent / "dashboard.html"


class MopsApi:
    """HTTP API server with Dashboard and status endpoints."""

    def __init__(
        self,
        port: int,
        host: str = "0.0.0.0",
        server_stats: TrafficStats | None = None,
        client_stats: TrafficStats | None = None,
        mode: str = "both",
        strategy: str = "random",
        server_host: str = "0.0.0.0",
        server_port: int = 10080,
        client_listen: str = "127.0.0.1",
        client_port: int = 10081,
        conn_tracker: ConnectionTracker | None = None,
        traffic_history: TrafficHistory | None = None,
    ) -> None:
        self.port = port
        self.host = host
        self._server_stats = server_stats
        self._client_stats = client_stats
        self._mode = mode
        self._strategy = strategy
        self._server_host = server_host
        self._server_port = server_port
        self._client_listen = client_listen
        self._client_port = client_port
        self._conn_tracker = conn_tracker
        self._traffic_history = traffic_history
        self._runner: web.AppRunner | None = None
        self._start_time = time.monotonic()

    def _snapshot(self, stats: TrafficStats) -> dict:
        hostname = socket.gethostname()
        nodes = []
        for name, ns in stats.get_all_nodes().items():
            if ns.ip == "server":
                nodes.append({
                    "ip": ns.ip,
                    "port": ns.port,
                    "hostname": hostname,
                    "fails": ns.fails,
                    "status": "active",
                    "up": ns.up,
                    "down": ns.down,
                })
            else:
                nodes.append({
                    "ip": ns.ip,
                    "port": ns.port,
                    "hostname": ns.ip,
                    "fails": ns.fails,
                    "status": "active",
                    "up": ns.up,
                    "down": ns.down,
                })
        speed_up, speed_down = (0, 0)
        if self._traffic_history:
            speed_up, speed_down = self._traffic_history.compute_speed()
        return {
            "nodes": nodes,
            "total_up": stats.get_total_up(),
            "total_down": stats.get_total_down(),
            "speed_up": speed_up,
            "speed_down": speed_down,
            "active_conns": stats.active_conns,
            "uptime": time.monotonic() - self._start_time,
        }

    async def _handle_server_status(self, request: web.Request) -> web.Response:
        if not self._server_stats:
            return web.json_response({"error": "Server stats not available"}, status=503)
        result = self._snapshot(self._server_stats)
        if self._conn_tracker:
            result["connections"] = self._conn_tracker.get_connections()
            result["active_conns"] = self._conn_tracker.active_count()
        else:
            result["connections"] = []
        return web.json_response(result)

    async def _handle_dashboard(self, request: web.Request) -> web.Response:
        # Serve built index.html from static/
        index = _STATIC_DIR / "index.html"
        if index.exists():
            return web.FileResponse(index)
        # Fallback to legacy dashboard.html
        html = _build_dashboard(
            mode=self._mode,
            strategy=self._strategy,
            server_host=self._server_host,
            server_port=self._server_port,
            client_listen=self._client_listen,
            client_port=self._client_port,
            show_server=bool(self._server_stats),
            show_client=bool(self._client_stats),
        )
        return web.Response(text=html, content_type="text/html")

    async def run(self) -> None:
        app = web.Application()
        app.router.add_get("/", self._handle_dashboard)
        app.router.add_get("/api/server", self._handle_server_status)
        app.router.add_get("/api/dashboard", self._handle_server_status)

        # Serve built frontend assets at root (dashboard.js, dashboard.css)
        if _STATIC_DIR.is_dir():
            app.router.add_static("/static", _STATIC_DIR)
            # Also serve individual assets at root for absolute paths in HTML
            for f in _STATIC_DIR.iterdir():
                if f.suffix in (".js", ".css"):
                    app.router.add_get(f"/{f.name}", lambda req, fp=f: web.FileResponse(fp))

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, self.host, self.port)
        await site.start()
        logger.info(f"API server listening on {self.host}:{self.port}")

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            logger.info("API server stopped")


def _build_dashboard(
    *,
    mode: str,
    strategy: str,
    server_host: str,
    server_port: int,
    client_listen: str,
    client_port: int,
    show_server: bool,
    show_client: bool,
) -> str:
    html = _DASHBOARD_HTML_PATH.read_text(encoding="utf-8")
    return html.replace("{MODE}", mode) \
        .replace("{STRATEGY}", strategy) \
        .replace("{SERVER_HOST}", server_host) \
        .replace("{SERVER_PORT}", str(server_port)) \
        .replace("{CLIENT_LISTEN}", client_listen) \
        .replace("{CLIENT_PORT}", str(client_port)) \
        .replace("{SHOW_SERVER}", "true" if show_server else "false") \
        .replace("{SHOW_CLIENT}", "true" if show_client else "false")
