"""End-to-end integration tests for MOPS."""

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mops.client import MopsClient
from mops.protocol import STRATEGY_RANDOM
from mops.scheduler import NodeInfo, Scheduler
from mops.server import MopsServer
from mops.stats import TrafficStats
from mops.tunnel import pipe, tunnel


class TestTunnel:
    """Test bidirectional traffic pipe."""

    @pytest.mark.asyncio
    async def test_pipe_basic(self):
        data = b"Hello, World!"
        reader = AsyncMockRead(data)
        writer = AsyncMockWrite()

        await pipe(reader, writer)
        assert writer.written == data

    @pytest.mark.asyncio
    async def test_pipe_empty(self):
        reader = AsyncMockRead(b"")
        writer = AsyncMockWrite()

        await pipe(reader, writer)
        assert writer.written == b""

    @pytest.mark.asyncio
    async def test_tunnel_bidirectional(self):
        r1 = AsyncMockRead(b"data1")
        w1 = AsyncMockWrite()
        r2 = AsyncMockRead(b"data2")
        w2 = AsyncMockWrite()

        await asyncio.wait_for(tunnel(r1, w1, r2, w2), timeout=2.0)

        # r1 -> w2 and r2 -> w1
        assert w2.written == b"data1"
        assert w1.written == b"data2"

    @pytest.mark.asyncio
    async def test_tunnel_with_stats(self):
        stats = TrafficStats()
        r1 = AsyncMockRead(b"test data")
        w1 = AsyncMockWrite()
        r2 = AsyncMockRead(b"")
        w2 = AsyncMockWrite()

        await asyncio.wait_for(
            tunnel(r1, w1, r2, w2, stats=stats, node_name="10.0.0.1:10080"),
            timeout=2.0,
        )

        ns = stats.get_node_stats("10.0.0.1:10080")
        assert ns is not None
        assert ns.down == 9  # r1 -> w2 (down)
        assert ns.up == 0  # r2 -> w1 (up) - r2 returns empty


class TestEndToEnd:
    """End-to-end tests with real TCP servers."""

    @pytest.mark.asyncio
    async def test_server_relay(self):
        """Test that MopsServer correctly relays traffic."""
        # Start a target echo server
        echo_data = b"echo response"
        target_server = await asyncio.start_server(
            lambda r, w: echo_handler(r, w, echo_data),
            "127.0.0.1", 0,
        )
        target_port = target_server.sockets[0].getsockname()[1]

        # Start MOPS server (mock zeroconf to avoid network binding)
        server = MopsServer(port=0)
        import socket
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            server_port = s.getsockname()[1]

        server.port = server_port

        # Mock mDNS to avoid network issues
        with patch.object(server._broadcaster, "register", new_callable=AsyncMock), \
             patch.object(server._broadcaster, "unregister", new_callable=AsyncMock):
            server_task = asyncio.create_task(server.run())
            await asyncio.sleep(0.5)

            try:
                # Connect to MOPS server
                reader, writer = await asyncio.open_connection("127.0.0.1", server_port)

                # Send tunnel header
                header = f"127.0.0.1:{target_port}\n"
                writer.write(header.encode())
                await writer.drain()

                # Send data
                writer.write(b"hello")
                await writer.drain()

                # Read response
                response = await asyncio.wait_for(reader.read(1024), timeout=2.0)
                assert response == echo_data

                writer.close()
                await writer.wait_closed()
            finally:
                await server.stop()
                server_task.cancel()
                target_server.close()
                await target_server.wait_closed()

    @pytest.mark.asyncio
    async def test_scheduler_with_real_server(self):
        """Test scheduler with multiple servers."""
        sched = Scheduler(strategy=STRATEGY_RANDOM)
        sched.add_node(NodeInfo(ip="127.0.0.1", port=10080))
        sched.add_node(NodeInfo(ip="127.0.0.1", port=20080))

        # Select multiple times - should get different nodes
        selected = set()
        for _ in range(50):
            node = sched.select()
            selected.add(node.port)

        # Random should hit both ports
        assert len(selected) >= 2


class TestTrafficStats:
    """Test traffic statistics."""

    def test_record_upload_download(self):
        stats = TrafficStats()
        stats.record_upload("10.0.0.1:10080", 100)
        stats.record_upload("10.0.0.1:10080", 200)
        stats.record_download("10.0.0.1:10080", 50)

        ns = stats.get_node_stats("10.0.0.1:10080")
        assert ns is not None
        assert ns.up == 300
        assert ns.down == 50

    def test_get_snapshot(self):
        stats = TrafficStats()
        stats.record_upload("10.0.0.1:10080", 1000)
        stats.record_download("10.0.0.1:10080", 2000)
        stats.active_conns = 3

        snap = stats.get_snapshot(mode="both", strategy="random")
        assert snap.mode == "both"
        assert snap.total_up == 1000
        assert snap.total_down == 2000
        assert snap.active_conns == 3
        assert len(snap.nodes) == 1

    def test_uptime(self):
        stats = TrafficStats()
        uptime = stats.get_uptime()
        assert uptime >= 0


# ── Test helpers ──


async def echo_handler(reader, writer, data):
    try:
        await reader.read(1024)
        writer.write(data)
        await writer.drain()
    except Exception:
        pass
    finally:
        writer.close()
        await writer.wait_closed()


class AsyncMockRead:
    """Minimal asyncio.StreamReader mock for testing pipe/tunnel."""

    def __init__(self, data: bytes):
        self._data = data
        self._pos = 0

    async def read(self, n: int = -1) -> bytes:
        if self._pos >= len(self._data):
            return b""
        if n == -1:
            result = self._data[self._pos:]
            self._pos = len(self._data)
        else:
            result = self._data[self._pos : self._pos + n]
            self._pos += n
        return result


class AsyncMockWrite:
    """Minimal asyncio.StreamWriter mock for testing pipe/tunnel."""

    def __init__(self):
        self.written = b""

    def write(self, data):
        self.written += data

    async def drain(self):
        pass

    def close(self):
        pass

    async def wait_closed(self):
        pass
