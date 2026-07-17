"""Standalone Dashboard service — discovers servers via mDNS, queries their APIs."""

from __future__ import annotations

import asyncio
import time

import aiohttp
from aiohttp import web
from loguru import logger

from .discovery import NodeDiscovery
from .protocol import DEFAULT_DASHBOARD_PORT, MAX_FAILS, MOPS_SERVICE_TYPE, NodeInfo
from .scheduler import Scheduler
from .stats import NodeRegistry, TrafficHistory
from .web import serve_index, setup_static_routes


class MopsDashboard:
    """Standalone dashboard that discovers servers via mDNS and queries their APIs."""

    def __init__(self, port: int = DEFAULT_DASHBOARD_PORT) -> None:
        self.port = port
        self._scheduler = Scheduler()
        self._registry = NodeRegistry()
        self._history = TrafficHistory()
        self._cache: dict[str, dict] = {}  # key = "ip:port"
        self._reachable: set[str] = set()  # keys with successful last query
        self._lock = asyncio.Lock()
        self._start_time = time.monotonic()
        self._discovery: NodeDiscovery | None = None
        self._runner: web.AppRunner | None = None
        self._http_session: aiohttp.ClientSession | None = None

    async def run(self) -> None:
        # Reusable HTTP session for querying server APIs
        timeout = aiohttp.ClientTimeout(total=3)
        self._http_session = aiohttp.ClientSession(timeout=timeout)

        # mDNS discovery
        self._discovery = NodeDiscovery(self._scheduler, registry=self._registry)
        self._discovery.start()
        logger.info("Dashboard mDNS discovery started")

        # Poll loop
        poll_task = asyncio.create_task(self._poll_loop())

        # Web server
        app = web.Application()
        app.router.add_get("/", self._handle_dashboard)
        app.router.add_get("/api/dashboard", self._handle_status)
        app.router.add_get("/api/server", self._handle_status)  # alias
        setup_static_routes(app)

        self._runner = web.AppRunner(app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "0.0.0.0", self.port)
        await site.start()
        logger.info(f"Dashboard listening on 0.0.0.0:{self.port}")

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            poll_task.cancel()
            if self._discovery:
                self._discovery.stop()

    async def _poll_loop(self) -> None:
        while True:
            try:
                await self._poll_loop_iteration()
            except Exception as e:
                logger.debug(f"Poll loop error: {e}")
            await asyncio.sleep(1)

    async def _poll_loop_iteration(self) -> None:
        nodes = self._scheduler.get_all_nodes()
        active_keys = {f"{n.ip}:{n.port}" for n in nodes}
        tasks = [self._query(n) for n in nodes]
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

        # Clean up stale entries
        async with self._lock:
            for key in list(self._reachable):
                if key not in active_keys:
                    self._reachable.discard(key)
            for key in list(self._cache):
                if key not in active_keys:
                    del self._cache[key]

        # Record aggregate snapshot
        total_up = sum(d.get("total_up", 0) for d in self._cache.values())
        total_down = sum(d.get("total_down", 0) for d in self._cache.values())
        conns = sum(d.get("active_conns", 0) for d in self._cache.values())
        self._history.record(total_up, total_down, conns)

        self._registry.prune()

    async def _query(self, node: NodeInfo) -> None:
        url = f"http://{node.ip}:{node.api_port}/api/server"
        key = f"{node.ip}:{node.port}"
        try:
            async with self._http_session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    async with self._lock:
                        self._cache[key] = data
                        self._reachable.add(key)
                else:
                    logger.debug(f"Query {url} returned status {resp.status}")
                    async with self._lock:
                        self._reachable.discard(key)
        except asyncio.TimeoutError:
            logger.debug(f"Query {url} timed out")
            async with self._lock:
                self._reachable.discard(key)
        except (ConnectionError, OSError) as e:
            logger.debug(f"Query {url} connection error: {e}")
            async with self._lock:
                self._reachable.discard(key)
        except Exception as e:
            logger.warning(f"Query {url} unexpected error: {type(e).__name__}: {e}")
            async with self._lock:
                self._reachable.discard(key)

    def _build_status(self) -> dict:
        nodes = []
        # Active nodes from scheduler (mDNS discovered)
        for info in self._scheduler.get_all_nodes():
            key = f"{info.ip}:{info.port}"
            cached = self._cache.get(key)
            status = "active" if key in self._reachable else "offline"
            nodes.append({
                "ip": info.ip,
                "port": info.port,
                "api_port": info.api_port,
                "hostname": info.hostname,
                "fails": info.fails,
                "status": status,
                "total_up": cached.get("total_up", 0) if cached else 0,
                "total_down": cached.get("total_down", 0) if cached else 0,
                "active_conns": cached.get("active_conns", 0) if cached else 0,
                "connections": cached.get("connections", []) if cached else [],
                "speed_up": cached.get("speed_up", 0) if cached else 0,
                "speed_down": cached.get("speed_down", 0) if cached else 0,
            })

        # Offline nodes from registry (not in current scheduler)
        current_keys = {f"{n['ip']}:{n['port']}" for n in nodes}
        for key, rec in self._registry.get_all().items():
            if key not in current_keys:
                nodes.append({
                    "ip": rec.ip,
                    "port": rec.port,
                    "api_port": rec.api_port,
                    "hostname": rec.hostname,
                    "fails": 0,
                    "status": "offline",
                    "total_up": 0,
                    "total_down": 0,
                    "active_conns": 0,
                    "connections": [],
                    "speed_up": 0,
                    "speed_down": 0,
                    "last_seen": rec.last_seen,
                })

        # Aggregate connections from all cached servers
        connections = []
        for key, data in self._cache.items():
            for c in data.get("connections", []):
                c["server_node"] = key
                connections.append(c)

        speed_up, speed_down = self._history.compute_speed()

        # Extract local_client from first server that reports it (both mode)
        local_client = None
        for data in self._cache.values():
            if data.get("local_client"):
                local_client = data["local_client"]
                break

        return {
            "nodes": nodes,
            "connections": connections,
            "total_up": sum(n.get("total_up", 0) for n in nodes),
            "total_down": sum(n.get("total_down", 0) for n in nodes),
            "speed_up": speed_up,
            "speed_down": speed_down,
            "active_conns": sum(d.get("active_conns", 0) for d in self._cache.values()),
            "uptime": time.monotonic() - self._start_time,
            "mode": "dashboard",
            "strategy": "mDNS",
            "local_client": local_client,
        }

    async def _handle_status(self, request: web.Request) -> web.Response:
        return web.json_response(self._build_status())

    async def _handle_dashboard(self, request: web.Request) -> web.Response:
        return await serve_index(request)

    async def stop(self) -> None:
        if self._http_session:
            await self._http_session.close()
        if self._discovery:
            self._discovery.stop()
        if self._runner:
            await self._runner.cleanup()
        logger.info("Dashboard stopped")
