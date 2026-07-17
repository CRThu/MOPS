"""Tests for MopsClient: SOCKS5, HTTP CONNECT, HTTP proxy, scheduling, circuit breaker."""

import asyncio
import json
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mops.client import MopsClient
from mops.scheduler import NoAvailableNodeError, NodeInfo, Scheduler
from mops.protocol import STRATEGY_RANDOM, STRATEGY_HASH, build_header

TEST_HOSTNAME = "test-host"


class TestScheduler:
    """Test load balancer and circuit breaker."""

    def test_add_remove_node(self):
        sched = Scheduler()
        node = NodeInfo(ip="192.168.1.1", port=10080, name="test")
        sched.add_node(node)
        assert len(sched.get_all_nodes()) == 1
        sched.remove_node("192.168.1.1:10080")
        assert len(sched.get_all_nodes()) == 0

    def test_random_strategy_distribution(self):
        sched = Scheduler(strategy=STRATEGY_RANDOM)
        for i in range(10):
            sched.add_node(NodeInfo(ip=f"192.168.1.{i}", port=10080))

        counts = {}
        for _ in range(1000):
            node = sched.select()
            key = f"{node.ip}:{node.port}"
            counts[key] = counts.get(key, 0) + 1

        # With random, each node should be selected at least once
        assert len(counts) == 10

    def test_hash_strategy_consistency(self):
        sched = Scheduler(strategy=STRATEGY_HASH)
        sched.add_node(NodeInfo(ip="10.0.0.1", port=10080))
        sched.add_node(NodeInfo(ip="10.0.0.2", port=10080))
        sched.add_node(NodeInfo(ip="10.0.0.3", port=10080))

        # Same input should always produce same output
        node1 = sched.select(client_ip="192.168.1.1", target_host="example.com")
        node2 = sched.select(client_ip="192.168.1.1", target_host="example.com")
        assert node1.ip == node2.ip

    def test_hash_strategy_fallback_to_random(self):
        """Hash strategy falls back to random when client_ip or target_host missing."""
        sched = Scheduler(strategy=STRATEGY_HASH)
        sched.add_node(NodeInfo(ip="10.0.0.1", port=10080))
        sched.add_node(NodeInfo(ip="10.0.0.2", port=10080))
        # Missing target_host — should still select a node (fallback)
        node = sched.select(client_ip="192.168.1.1")
        assert node.ip in ("10.0.0.1", "10.0.0.2")
        # Missing both — should still select
        node2 = sched.select()
        assert node2.ip in ("10.0.0.1", "10.0.0.2")

    def test_circuit_breaker(self):
        sched = Scheduler()
        node = NodeInfo(ip="10.0.0.1", port=10080)
        sched.add_node(node)

        # Report 2 fails -> circuit breaker triggers
        sched.report_fail(node)
        sched.report_fail(node)
        assert len(sched.get_active_nodes()) == 0

    def test_report_fail_nonexistent_node(self):
        sched = Scheduler()
        node = NodeInfo(ip="10.0.0.99", port=9999)
        # Should not crash when reporting fail for a node not in the pool
        sched.report_fail(node)

    def test_circuit_breaker_recovery(self):
        import time
        sched = Scheduler()
        node = NodeInfo(ip="10.0.0.1", port=10080)
        sched.add_node(node)

        sched.report_fail(node)
        sched.report_fail(node)
        assert len(sched.get_active_nodes()) == 0

        # Simulate time passing
        node.last_fail = time.monotonic() - 31  # > RECOVERY_INTERVAL
        sched.recover_nodes()
        assert len(sched.get_active_nodes()) == 1

    def test_no_available_node(self):
        sched = Scheduler()
        with pytest.raises(NoAvailableNodeError):
            sched.select()

    def test_update_node(self):
        sched = Scheduler()
        node = NodeInfo(ip="10.0.0.1", port=10080, weight=1)
        sched.add_node(node)
        node.weight = 2
        sched.add_node(node)
        assert len(sched.get_all_nodes()) == 1

    def test_remove_by_name(self):
        sched = Scheduler()
        node = NodeInfo(ip="10.0.0.1", port=10080, name="mops-server-1-10080._mops-proxy._tcp.local.")
        sched.add_node(node)
        sched.remove_by_name("mops-server-1-10080._mops-proxy._tcp.local.")
        assert len(sched.get_all_nodes()) == 0


class TestSOCKS5Parsing:
    """Test SOCKS5 protocol handling."""

    def _build_socks5_connect(self, host: str, port: int, atyp: int = 0x03) -> bytes:
        """Build a SOCKS5 CONNECT request."""
        # Auth negotiation
        auth = b"\x05\x01\x00"  # VER=5, NMETHODS=1, METHOD=0

        # CONNECT request
        if atyp == 0x01:  # IPv4
            addr = bytes(int(x) for x in host.split("."))
            header = struct.pack("BBBB", 5, 1, 0, atyp) + addr
        elif atyp == 0x03:  # Domain
            header = struct.pack("BBBB", 5, 1, 0, atyp)
            header += bytes([len(host)]) + host.encode()
        elif atyp == 0x04:  # IPv6
            header = struct.pack("BBBB", 5, 1, 0, atyp)
            header += bytes.fromhex(host.replace(":", ""))
        else:
            raise ValueError(f"Unsupported ATYP: {atyp}")

        header += struct.pack("!H", port)
        return auth + header

    @pytest.mark.asyncio
    async def test_socks5_connect_ipv4(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        request = self._build_socks5_connect("1.2.3.4", 80, atyp=0x01)

        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.read = AsyncMock(return_value=b"\x05")
        reader.readline = AsyncMock()
        reader.readexactly = AsyncMock()

        # Simulate readexactly returning chunks
        chunks = [
            b"\x01",  # NMETHODS
            b"\x00",  # METHOD
            b"\x05\x01\x00\x01",  # VER CMD RSV ATYP
            bytes([1, 2, 3, 4]),  # IPv4
            struct.pack("!H", 80),  # PORT
        ]
        call_count = 0
        async def mock_readexactly(n):
            nonlocal call_count
            result = chunks[call_count]
            call_count += 1
            return result

        reader.readexactly = mock_readexactly

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        with patch("mops.client.MopsClient._connect_and_tunnel", new_callable=AsyncMock) as mock_connect:
            await client._handle_socks5(reader, writer, b"\x05")
            mock_connect.assert_called_once()
            args = mock_connect.call_args
            assert args[0][2] == "1.2.3.4"
            assert args[0][3] == 80

    @pytest.mark.asyncio
    async def test_socks5_connect_domain(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        chunks = [
            b"\x01",  # NMETHODS
            b"\x00",  # METHOD
            b"\x05\x01\x00\x03",  # VER CMD RSV ATYP (domain)
            b"\x0b",  # domain length
            b"example.com",  # domain
            struct.pack("!H", 443),  # PORT
        ]
        call_count = 0
        async def mock_readexactly(n):
            nonlocal call_count
            result = chunks[call_count]
            call_count += 1
            return result

        reader.readexactly = mock_readexactly

        with patch("mops.client.MopsClient._connect_and_tunnel", new_callable=AsyncMock) as mock_connect:
            await client._handle_socks5(reader, writer, b"\x05")
            mock_connect.assert_called_once()
            args = mock_connect.call_args
            assert args[0][2] == "example.com"
            assert args[0][3] == 443


class TestHTTPRouting:
    """Test HTTP protocol routing (CONNECT vs plain HTTP)."""

    @pytest.mark.asyncio
    async def test_handle_http_routes_connect(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch.object(client, "_handle_http_connect", new_callable=AsyncMock) as mock_connect:
            await client._handle_http(reader, writer, b"CONNECT example.com:443 HTTP/1.1\r\n")
            mock_connect.assert_called_once_with(reader, writer, "example.com:443")

    @pytest.mark.asyncio
    async def test_handle_http_routes_get(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch.object(client, "_handle_http_request", new_callable=AsyncMock) as mock_req:
            await client._handle_http(reader, writer, b"GET http://example.com/path HTTP/1.1\r\n")
            mock_req.assert_called_once_with(reader, writer, "GET", "http://example.com/path", b"GET http://example.com/path HTTP/1.1\r\n")

    @pytest.mark.asyncio
    async def test_handle_http_routes_post(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch.object(client, "_handle_http_request", new_callable=AsyncMock) as mock_req:
            await client._handle_http(reader, writer, b"POST http://example.com/api HTTP/1.1\r\n")
            mock_req.assert_called_once_with(reader, writer, "POST", "http://example.com/api", b"POST http://example.com/api HTTP/1.1\r\n")

    @pytest.mark.asyncio
    async def test_handle_http_bad_request(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        await client._handle_http(reader, writer, b"BAD\r\n")
        writer.write.assert_called_once_with(b"HTTP/1.1 400 Bad Request\r\n\r\n")


class TestHTTPCONNECT:
    """Test HTTP CONNECT proxy handling."""

    @pytest.mark.asyncio
    async def test_http_connect_parsing(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        # Simulate reading headers until \r\n\r\n
        header_lines = [
            b"Host: example.com:443\r\n",
            b"Proxy-Connection: keep-alive\r\n",
            b"\r\n",
        ]
        line_idx = 0
        async def mock_readline():
            nonlocal line_idx
            if line_idx < len(header_lines):
                result = header_lines[line_idx]
                line_idx += 1
                return result
            return b""

        reader.readline = mock_readline

        with patch("mops.client.MopsClient._connect_and_tunnel", new_callable=AsyncMock) as mock_connect:
            await client._handle_http_connect(reader, writer, "example.com:443")
            mock_connect.assert_called_once()
            args = mock_connect.call_args
            assert args[0][2] == "example.com"
            assert args[0][3] == 443


class TestHTTPRequest:
    """Test plain HTTP proxy (GET/POST/etc)."""

    @pytest.fixture(autouse=True)
    def mock_hostname(self):
        with patch("mops.client.socket.gethostname", return_value=TEST_HOSTNAME):
            yield

    @pytest.mark.asyncio
    async def test_http_get_request(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        header_lines = [
            b"Host: httpbin.org\r\n",
            b"User-Agent: curl/7.0\r\n",
            b"\r\n",
        ]
        line_idx = 0
        async def mock_readline():
            nonlocal line_idx
            if line_idx < len(header_lines):
                result = header_lines[line_idx]
                line_idx += 1
                return result
            return b""

        reader.readline = mock_readline

        mock_server_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_server_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_server_writer.write = MagicMock()
        mock_server_writer.drain = AsyncMock()

        with patch("mops.client.asyncio.open_connection", new_callable=AsyncMock, return_value=(mock_server_reader, mock_server_writer)), \
             patch("mops.client.tunnel", new_callable=AsyncMock) as mock_tunnel:
            await client._handle_http_request(
                reader, writer, "GET", "http://httpbin.org/ip", b"GET http://httpbin.org/ip HTTP/1.1\r\n"
            )
            # Verify tunnel header sent
            mock_server_writer.write.assert_any_call(build_header("httpbin.org", 80, 10081, TEST_HOSTNAME))
            # Verify rewritten request was sent (GET /ip not GET http://httpbin.org/ip)
            mock_server_writer.write.assert_any_call(b"GET /ip HTTP/1.1\r\n")
            # Verify tunnel was called
            mock_tunnel.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_post_request(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        header_lines = [
            b"Host: api.example.com\r\n",
            b"Content-Type: application/json\r\n",
            b"Content-Length: 2\r\n",
            b"\r\n",
        ]
        line_idx = 0
        async def mock_readline():
            nonlocal line_idx
            if line_idx < len(header_lines):
                result = header_lines[line_idx]
                line_idx += 1
                return result
            return b""

        reader.readline = mock_readline
        reader.read = AsyncMock(return_value=b"{}")

        mock_server_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_server_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_server_writer.write = MagicMock()
        mock_server_writer.drain = AsyncMock()

        with patch("mops.client.asyncio.open_connection", new_callable=AsyncMock, return_value=(mock_server_reader, mock_server_writer)), \
             patch("mops.client.tunnel", new_callable=AsyncMock) as mock_tunnel:
            await client._handle_http_request(
                reader, writer, "POST", "http://api.example.com/data", b"POST http://api.example.com/data HTTP/1.1\r\n"
            )
            mock_server_writer.write.assert_any_call(build_header("api.example.com", 80, 10081, TEST_HOSTNAME))
            mock_server_writer.write.assert_any_call(b"POST /data HTTP/1.1\r\n")
            mock_tunnel.assert_called_once()

    @pytest.mark.asyncio
    async def test_http_request_no_nodes(self):
        client = MopsClient(listen_port=10081)

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        await client._handle_http_request(
            reader, writer, "GET", "http://example.com/", b"GET http://example.com/ HTTP/1.1\r\n"
        )
        writer.write.assert_called_once_with(b"HTTP/1.1 503 Service Unavailable\r\n\r\n")

    @pytest.mark.asyncio
    async def test_http_request_with_query_string(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        header_lines = [b"\r\n"]
        line_idx = 0
        async def mock_readline():
            nonlocal line_idx
            if line_idx < len(header_lines):
                result = header_lines[line_idx]
                line_idx += 1
                return result
            return b""
        reader.readline = mock_readline

        mock_server_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_server_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_server_writer.write = MagicMock()
        mock_server_writer.drain = AsyncMock()

        with patch("mops.client.asyncio.open_connection", new_callable=AsyncMock, return_value=(mock_server_reader, mock_server_writer)), \
             patch("mops.client.tunnel", new_callable=AsyncMock):
            await client._handle_http_request(
                reader, writer, "GET", "http://api.example.com/search?q=test&page=1",
                b"GET http://api.example.com/search?q=test&page=1 HTTP/1.1\r\n"
            )
            mock_server_writer.write.assert_any_call(build_header("api.example.com", 80, 10081, TEST_HOSTNAME))
            mock_server_writer.write.assert_any_call(b"GET /search?q=test&page=1 HTTP/1.1\r\n")

    @pytest.mark.asyncio
    async def test_http_request_custom_port(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        header_lines = [b"\r\n"]
        line_idx = 0
        async def mock_readline():
            nonlocal line_idx
            if line_idx < len(header_lines):
                result = header_lines[line_idx]
                line_idx += 1
                return result
            return b""
        reader.readline = mock_readline

        mock_server_reader = AsyncMock(spec=asyncio.StreamReader)
        mock_server_writer = AsyncMock(spec=asyncio.StreamWriter)
        mock_server_writer.write = MagicMock()
        mock_server_writer.drain = AsyncMock()

        with patch("mops.client.asyncio.open_connection", new_callable=AsyncMock, return_value=(mock_server_reader, mock_server_writer)), \
             patch("mops.client.tunnel", new_callable=AsyncMock):
            await client._handle_http_request(
                reader, writer, "GET", "http://internal.dev:8080/api",
                b"GET http://internal.dev:8080/api HTTP/1.1\r\n"
            )
            mock_server_writer.write.assert_any_call(build_header("internal.dev", 8080, 10081, TEST_HOSTNAME))
            mock_server_writer.write.assert_any_call(b"GET /api HTTP/1.1\r\n")

    @pytest.mark.asyncio
    async def test_http_request_connection_error(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        header_lines = [b"\r\n"]
        line_idx = 0
        async def mock_readline():
            nonlocal line_idx
            if line_idx < len(header_lines):
                result = header_lines[line_idx]
                line_idx += 1
                return result
            return b""
        reader.readline = mock_readline

        with patch("mops.client.asyncio.open_connection", new_callable=AsyncMock, side_effect=ConnectionError("refused")), \
             patch("mops.client.Scheduler.report_fail") as mock_fail:
            await client._handle_http_request(
                reader, writer, "GET", "http://example.com/", b"GET http://example.com/ HTTP/1.1\r\n"
            )
            writer.write.assert_called_once_with(b"HTTP/1.1 502 Bad Gateway\r\n\r\n")
            mock_fail.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_http_short_line(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        await client._handle_http(reader, writer, b"BAD\r\n")
        writer.write.assert_called_once_with(b"HTTP/1.1 400 Bad Request\r\n\r\n")


class TestMopsClient:
    """Test client lifecycle."""

    @pytest.mark.asyncio
    async def test_handle_proxy_socks5(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.read = AsyncMock(return_value=b"\x05")
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch.object(client, "_handle_socks5", new_callable=AsyncMock) as mock_socks5:
            await client.handle_proxy(reader, writer)
            mock_socks5.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_proxy_http_connect(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.read = AsyncMock(return_value=b"C")
        reader.readline = AsyncMock(return_value=b"ONNECT example.com:443 HTTP/1.1\r\n")
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch.object(client, "_handle_http", new_callable=AsyncMock) as mock_http:
            await client.handle_proxy(reader, writer)
            mock_http.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_proxy_http_get(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.read = AsyncMock(return_value=b"G")
        reader.readline = AsyncMock(return_value=b"ET http://example.com/ HTTP/1.1\r\n")
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch.object(client, "_handle_http", new_callable=AsyncMock) as mock_http:
            await client.handle_proxy(reader, writer)
            mock_http.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_proxy_empty(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.read = AsyncMock(return_value=b"")
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await client.handle_proxy(reader, writer)
        writer.close.assert_called()
        writer.wait_closed.assert_called()
