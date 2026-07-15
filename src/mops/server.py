"""MOPS Server: TCP relay + mDNS broadcast."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger
from zeroconf import ServiceInfo, Zeroconf

from .protocol import (
    BUFFER_SIZE,
    DEFAULT_API_PORT,
    MOPS_SERVICE_TYPE,
    SERVICE_NAME_PREFIX,
    parse_header,
)
from .tunnel import tunnel

if TYPE_CHECKING:
    from .stats import ConnectionTracker, TrafficStats

CONNECT_TIMEOUT = 10


class MdnsBroadcaster:
    """Manages mDNS service registration and unregistration."""

    def __init__(self) -> None:
        self._zc: Zeroconf | None = None
        self._service_info: ServiceInfo | None = None

    async def register(self, port: int, api_port: int = DEFAULT_API_PORT, weight: int = 1, ttl: int = 60, bind: str = "") -> None:
        import socket

        hostname = socket.gethostname()
        service_name = f"{SERVICE_NAME_PREFIX}{hostname}-{port}.{MOPS_SERVICE_TYPE}"

        if bind:
            # User specified bind address
            addresses = [socket.inet_aton(bind)]
        else:
            # Auto-detect: prefer LAN IPs, avoid virtual adapters
            addresses = self._detect_lan_ip()

        self._zc = Zeroconf()

        properties = {
            b"weight": str(weight).encode(),
            b"api_port": str(api_port).encode(),
        }

        self._service_info = ServiceInfo(
            type_=MOPS_SERVICE_TYPE,
            name=service_name,
            port=port,
            properties=properties,
            addresses=addresses,
            host_ttl=ttl,
        )
        await self._zc.async_register_service(self._service_info)
        resolved_ip = socket.inet_ntoa(addresses[0])
        logger.info(f"mDNS service registered: {service_name} -> {resolved_ip}:{port} (TTL={ttl}s)")

    @staticmethod
    def _detect_lan_ip() -> list:
        """Detect LAN IP via routing table (UDP connect to public IP)."""
        import socket

        # Primary: routing-based detection — OS picks the real出口网卡
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return [socket.inet_aton(ip)]
        except Exception:
            pass

        # Fallback: enumerate all non-loopback interfaces
        candidates = []
        excluded = ("127.", "0.", "224.", "169.254.")
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if not any(ip.startswith(p) for p in excluded):
                    candidates.append(socket.inet_aton(ip))
        except Exception:
            pass

        if not candidates:
            logger.warning("No LAN IP detected, falling back to 127.0.0.1 (mDNS won't be reachable from other machines)")
        return candidates or [socket.inet_aton("127.0.0.1")]

    async def unregister(self) -> None:
        if self._zc and self._service_info:
            try:
                await self._zc.async_unregister_service(self._service_info)
            except Exception as e:
                logger.debug(f"mDNS unregister service warning: {e}")
            try:
                self._zc.close()
            except Exception as e:
                logger.debug(f"mDNS close warning: {e}")
            self._service_info = None
            self._zc = None
            logger.info("mDNS service unregistered")


class MopsServer:
    """TCP relay server that forwards traffic through tunnels."""

    def __init__(
        self,
        port: int,
        api_port: int = DEFAULT_API_PORT,
        weight: int = 1,
        mdns_ttl: int = 60,
        bind: str = "",
        stats: TrafficStats | None = None,
        conn_tracker: ConnectionTracker | None = None,
    ) -> None:
        self.port = port
        self.api_port = api_port
        self.weight = weight
        self.mdns_ttl = mdns_ttl
        self.bind = bind
        self._broadcaster = MdnsBroadcaster()
        self._server: asyncio.Server | None = None
        self._stats = stats
        self._conn_tracker = conn_tracker

    async def handle_client(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        peer_ip = peer[0] if peer else "unknown"
        logger.debug(f"New connection from {peer}")

        conn_id: str | None = None
        target_writer: asyncio.StreamWriter | None = None
        error_reason = ""
        try:
            header = await reader.readline()
            if not header:
                return

            try:
                host, port, client_port, client_host = parse_header(header)
            except (ValueError, KeyError) as e:
                logger.warning(f"Invalid header from {peer}: {e}")
                return

            if self._conn_tracker:
                conn_id = self._conn_tracker.start(peer_ip, host, port, client_port=client_port, client_host=client_host)

            logger.debug(f"Connecting to {host}:{port}")
            try:
                target_reader, target_writer = await asyncio.wait_for(
                    asyncio.open_connection(host, port),
                    timeout=CONNECT_TIMEOUT,
                )
            except asyncio.TimeoutError:
                error_reason = f"connect-timeout ({host}:{port})"
                logger.warning(f"Connect timeout to {host}:{port} from {peer}")
                return
            except (ConnectionError, OSError) as e:
                error_reason = f"connect-failed ({e})"
                logger.warning(f"Connect failed to {host}:{port} from {peer}: {e}")
                return

            tunnel_reason = await tunnel(
                reader, writer, target_reader, target_writer,
                stats=self._stats, node_name=f"server:{self.port}",
                tag=f"{peer_ip}->{host}:{port}",
            )
            if tunnel_reason and tunnel_reason != "eof":
                error_reason = tunnel_reason
                if "timeout" in tunnel_reason:
                    logger.warning(f"Tunnel timeout {peer_ip}->{host}:{port}: {tunnel_reason}")
                elif "dns" in tunnel_reason:
                    logger.warning(f"Tunnel DNS error {peer_ip}->{host}:{port}: {tunnel_reason}")
        except asyncio.IncompleteReadError:
            error_reason = "incomplete-read"
        except Exception as e:
            error_reason = f"unexpected:{type(e).__name__}"
            logger.error(f"Unexpected error in handle_client from {peer}: {type(e).__name__}: {e}")
        finally:
            if self._conn_tracker and conn_id:
                self._conn_tracker.end(conn_id, error_reason=error_reason)
            if target_writer:
                target_writer.close()
                try:
                    await target_writer.wait_closed()
                except (ConnectionError, OSError, RuntimeError):
                    pass
            writer.close()
            try:
                await writer.wait_closed()
            except (ConnectionError, OSError, RuntimeError):
                pass

    async def run(self) -> None:
        """Start the server and mDNS broadcast."""
        self._server = await asyncio.start_server(
            self.handle_client, "0.0.0.0", self.port
        )
        logger.info(f"Server listening on 0.0.0.0:{self.port}")

        await self._broadcaster.register(self.port, self.api_port, self.weight, self.mdns_ttl, self.bind)

        async with self._server:
            try:
                await self._server.serve_forever()
            except asyncio.CancelledError:
                pass

    async def stop(self) -> None:
        """Stop the server and unregister mDNS."""
        await self._broadcaster.unregister()
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("Server stopped")
