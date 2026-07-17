"""MOPS Client: SOCKS5 + HTTP proxy (CONNECT & plain) with load-balanced tunneling."""

from __future__ import annotations

import asyncio
import socket
import struct
from loguru import logger

from .discovery import NodeDiscovery
from .protocol import STRATEGY_RANDOM, build_header
from .scheduler import NoAvailableNodeError, Scheduler
from .stats import TrafficStats
from .tunnel import tunnel


class MopsClient:
    """Proxy client that discovers servers via mDNS and load-balances connections."""

    def __init__(
        self,
        listen_port: int,
        listen_host: str = "127.0.0.1",
        strategy: str = STRATEGY_RANDOM,
        stats: TrafficStats | None = None,
    ) -> None:
        self.listen_port = listen_port
        self.listen_host = listen_host
        self._hostname = socket.gethostname()
        self._scheduler = Scheduler(strategy)
        self._discovery = NodeDiscovery(self._scheduler)
        self._server: asyncio.Server | None = None
        self._stats = stats
        self._strategy = strategy

    async def handle_proxy(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        peer = writer.get_extra_info("peername")
        logger.debug(f"New proxy connection from {peer}")

        try:
            # Peek at first byte to detect protocol
            first_byte = await reader.read(1)
            if not first_byte:
                writer.close()
                await writer.wait_closed()
                return

            if first_byte[0] == 0x05:
                await self._handle_socks5(reader, writer, first_byte)
            else:
                # HTTP: we already consumed the first byte, need to put it back
                rest = await reader.readline()
                first_line = first_byte + rest
                await self._handle_http(reader, writer, first_line)
        except asyncio.IncompleteReadError:
            pass
        except (ConnectionError, OSError) as e:
            winerror = getattr(e, "winerror", None)
            if winerror not in (10054,):  # 10054 = normal connection reset
                logger.debug(f"Proxy connection error from {peer}: {e}")
        except Exception as e:
            logger.error(f"Unexpected error in handle_proxy: {type(e).__name__}: {e}")
        finally:
            writer.close()
            try:
                await asyncio.wait_for(writer.wait_closed(), timeout=3)
            except (ConnectionError, OSError, RuntimeError, asyncio.TimeoutError, asyncio.CancelledError):
                pass

    async def _handle_socks5(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        first_byte: bytes,
    ) -> None:
        # SOCKS5 handshake: VER(1) + NMETHODS(1) + METHODS(n)
        header = await reader.readexactly(1)  # NMETHODS
        nmethods = header[0]
        await reader.readexactly(nmethods)  # METHODS

        # Reply: VER=0x05, METHOD=0x00 (no auth)
        writer.write(b"\x05\x00")
        await writer.drain()

        # SOCKS5 CONNECT request
        # VER(1) + CMD(1) + RSV(1) + ATYP(1) + ADDR(var) + PORT(2)
        req = await reader.readexactly(4)
        ver, cmd, rsv, atyp = struct.unpack("BBBB", req)

        if ver != 0x05:
            logger.warning(f"Invalid SOCKS5 version: {ver}")
            writer.write(b"\x05\x01\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            return

        if cmd != 0x01:  # Only CONNECT supported
            logger.warning(f"Unsupported SOCKS5 command: {cmd}")
            writer.write(b"\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            return

        # Parse address
        if atyp == 0x01:  # IPv4
            addr_data = await reader.readexactly(4)
            target_host = ".".join(str(b) for b in addr_data)
        elif atyp == 0x03:  # Domain
            domain_len = (await reader.readexactly(1))[0]
            domain_data = await reader.readexactly(domain_len)
            target_host = domain_data.decode()
        elif atyp == 0x04:  # IPv6
            addr_data = await reader.readexactly(16)
            target_host = ":".join(
                f"{addr_data[i]:02x}{addr_data[i+1]:02x}" for i in range(0, 16, 2)
            )
        else:
            logger.warning(f"Unsupported SOCKS5 ATYP: {atyp}")
            writer.write(b"\x05\x08\x00\x01\x00\x00\x00\x00\x00\x00")
            await writer.drain()
            return

        port_data = await reader.readexactly(2)
        target_port = struct.unpack("!H", port_data)[0]

        logger.debug(f"SOCKS5 CONNECT: {target_host}:{target_port}")

        # Send SOCKS5 success reply: VER=5, REP=0, RSV=0, ATYP=1, BND.ADDR=0.0.0.0, BND.PORT=0
        writer.write(b"\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00")
        await writer.drain()

        await self._connect_and_tunnel(reader, writer, target_host, target_port)

    async def _handle_http(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        first_line: bytes,
    ) -> None:
        line = first_line.decode(errors="ignore").strip()
        parts = line.split()
        if len(parts) < 3:
            writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await writer.drain()
            return

        method = parts[0].upper()
        url = parts[1]

        if method == "CONNECT":
            await self._handle_http_connect(reader, writer, url)
        else:
            await self._handle_http_request(reader, writer, method, url, first_line)

    async def _handle_http_connect(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        addr: str,
    ) -> None:
        if ":" in addr:
            host, port_str = addr.rsplit(":", 1)
            port = int(port_str)
        else:
            host = addr
            port = 443

        # Read remaining headers until \r\n\r\n (with timeout to prevent slowloris)
        try:
            while True:
                line = await asyncio.wait_for(reader.readline(), timeout=10)
                if line == b"\r\n" or not line:
                    break
        except asyncio.TimeoutError:
            logger.warning(f"HTTP CONNECT header read timeout from {writer.get_extra_info('peername')}")
            writer.write(b"HTTP/1.1 408 Request Timeout\r\n\r\n")
            await writer.drain()
            return

        logger.debug(f"HTTP CONNECT: {host}:{port}")

        writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await writer.drain()

        await self._connect_and_tunnel(reader, writer, host, port)

    async def _handle_http_request(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        method: str,
        url: str,
        first_line: bytes,
    ) -> None:
        """Handle plain HTTP proxy: GET http://host/path → connect to host, forward as GET /path."""
        from urllib.parse import urlparse

        parsed = urlparse(url)

        # Only support http/https URLs
        if parsed.scheme and parsed.scheme.lower() not in ("http", "https"):
            logger.warning(f"Unsupported URL scheme: {parsed.scheme}")
            client_writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await client_writer.drain()
            return

        host = parsed.hostname
        port = parsed.port or 80
        path = parsed.path or "/"
        if parsed.query:
            path += "?" + parsed.query

        if not host:
            client_writer.write(b"HTTP/1.1 400 Bad Request\r\n\r\n")
            await client_writer.drain()
            return

        logger.debug(f"HTTP {method}: {host}:{port}{path}")

        try:
            node = self._scheduler.select(target_host=host)
        except NoAvailableNodeError:
            logger.error("No available nodes for tunneling")
            client_writer.write(b"HTTP/1.1 503 Service Unavailable\r\n\r\n")
            await client_writer.drain()
            return

        node_key = f"{node.ip}:{node.port}"

        try:
            try:
                server_reader, server_writer = await asyncio.wait_for(
                    asyncio.open_connection(node.ip, node.port),
                    timeout=10,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Connect timeout to server {node_key}")
                self._scheduler.report_fail(node)
                client_writer.write(b"HTTP/1.1 504 Gateway Timeout\r\n\r\n")
                await client_writer.drain()
                return
            except (ConnectionError, OSError) as e:
                logger.warning(f"Connect failed to server {node_key}: {e}")
                self._scheduler.report_fail(node)
                client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
                await client_writer.drain()
                return

            # Send tunnel header
            header = build_header(host, port, self.listen_port, self._hostname)
            server_writer.write(header)
            await server_writer.drain()

            # Read full request from client
            request_lines = [first_line]
            while True:
                line = await client_reader.readline()
                request_lines.append(line)
                if line == b"\r\n" or not line:
                    break

            # Rewrite request: change absolute URL to path
            original_line = first_line.decode(errors="ignore").strip()
            first_parts = original_line.split(None, 2)
            new_first_line = f"{first_parts[0]} {path} {first_parts[2]}\r\n"
            request_lines[0] = new_first_line.encode()

            # Forward rewritten request to server
            for line in request_lines:
                server_writer.write(line)
            await server_writer.drain()

            # Bidirectional tunnel
            if self._stats:
                self._stats.active_conns += 1
            try:
                await tunnel(
                    client_reader, client_writer,
                    server_reader, server_writer,
                    stats=self._stats, node_name=node_key,
                )
            finally:
                if self._stats:
                    self._stats.active_conns -= 1

        except (ConnectionError, OSError) as e:
            logger.warning(f"Tunnel connection failed to {node_key}: {e}")
            self._scheduler.report_fail(node)
            client_writer.write(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            await client_writer.drain()

    async def _connect_and_tunnel(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        target_host: str,
        target_port: int,
    ) -> None:
        try:
            node = self._scheduler.select(target_host=target_host)
        except NoAvailableNodeError:
            logger.error("No available nodes for tunneling")
            client_writer.write(b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00")
            await client_writer.drain()
            return

        node_key = f"{node.ip}:{node.port}"

        try:
            # Connect to the selected server with timeout
            try:
                server_reader, server_writer = await asyncio.wait_for(
                    asyncio.open_connection(node.ip, node.port),
                    timeout=10,
                )
            except asyncio.TimeoutError:
                logger.warning(f"Connect timeout to server {node_key}")
                self._scheduler.report_fail(node)
                if self._stats:
                    self._stats.update_node_fails(node_key, node.fails)
                # Send SOCKS5 error reply (host unreachable)
                client_writer.write(b"\x05\x04\x00\x01\x00\x00\x00\x00\x00\x00")
                await client_writer.drain()
                return

            # Send tunnel header
            header = build_header(target_host, target_port, self.listen_port, self._hostname)
            server_writer.write(header)
            await server_writer.drain()

            # Bidirectional tunnel
            if self._stats:
                self._stats.active_conns += 1
            try:
                tunnel_reason = await tunnel(
                    client_reader, client_writer,
                    server_reader, server_writer,
                    stats=self._stats, node_name=node_key,
                    tag=f"client->{node_key}",
                )
                if tunnel_reason and tunnel_reason != "eof":
                    logger.debug(f"Tunnel closed {node_key}: {tunnel_reason}")
            finally:
                if self._stats:
                    self._stats.active_conns -= 1

        except (ConnectionError, OSError) as e:
            logger.warning(f"Tunnel connection failed to {node_key}: {e}")
            self._scheduler.report_fail(node)
            if self._stats:
                self._stats.update_node_fails(node_key, node.fails)

    async def run(self) -> None:
        """Start discovery, TCP server, and recovery timer."""
        self._discovery.start()
        logger.info(
            f"Client listening on {self.listen_host}:{self.listen_port} "
            f"(strategy={self._strategy})"
        )

        self._server = await asyncio.start_server(
            self.handle_proxy, self.listen_host, self.listen_port
        )

        # Recovery timer
        recovery_task = asyncio.create_task(self._recovery_loop())

        async with self._server:
            try:
                await self._server.serve_forever()
            except asyncio.CancelledError:
                pass
            finally:
                recovery_task.cancel()

    async def _recovery_loop(self) -> None:
        from .protocol import RECOVERY_INTERVAL
        while True:
            try:
                await asyncio.sleep(RECOVERY_INTERVAL)
                self._scheduler.recover_nodes()
            except asyncio.CancelledError:
                return
            except Exception as e:
                logger.error(f"Recovery loop error: {type(e).__name__}: {e}")

    async def stop(self) -> None:
        self._discovery.stop()
        if self._server:
            self._server.close()
            try:
                await asyncio.wait_for(self._server.wait_closed(), timeout=5)
            except asyncio.TimeoutError:
                logger.warning("Client wait_closed timed out, forcing stop")
            logger.info("Client stopped")
