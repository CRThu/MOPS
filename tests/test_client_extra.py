"""Additional client tests for better coverage."""

import asyncio
import struct
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mops.client import MopsClient
from mops.scheduler import NodeInfo, Scheduler


class TestSOCKS5IPv6:
    @pytest.mark.asyncio
    async def test_socks5_connect_ipv6(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        # IPv6 address: 2001:db8::1
        ipv6_bytes = bytes.fromhex("20010db8000000000000000000000001")

        chunks = [
            b"\x01",  # NMETHODS
            b"\x00",  # METHOD
            b"\x05\x01\x00\x04",  # VER CMD RSV ATYP (IPv6)
            ipv6_bytes,
            struct.pack("!H", 443),
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
            # IPv6 should be formatted as hex groups
            assert ":" in args[0][2]  # host should contain colons
            assert args[0][3] == 443

    @pytest.mark.asyncio
    async def test_socks5_invalid_atyp(self):
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
            b"\x05\x01\x00\x05",  # VER CMD RSV ATYP (invalid)
            b"\x00\x00\x00\x00",  # dummy addr
            struct.pack("!H", 80),
        ]
        call_count = 0
        async def mock_readexactly(n):
            nonlocal call_count
            result = chunks[call_count]
            call_count += 1
            return result

        reader.readexactly = mock_readexactly

        await client._handle_socks5(reader, writer, b"\x05")
        # Should send error response
        writer.write.assert_called()


class TestHTTPConnectEdgeCases:
    @pytest.mark.asyncio
    async def test_http_connect_no_port(self):
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

        with patch("mops.client.MopsClient._connect_and_tunnel", new_callable=AsyncMock) as mock_connect:
            await client._handle_http_connect(reader, writer, "example.com")
            mock_connect.assert_called_once()
            args = mock_connect.call_args
            assert args[0][2] == "example.com"
            assert args[0][3] == 443  # default port

    @pytest.mark.asyncio
    async def test_http_connect_full_url(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
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

        with patch("mops.client.MopsClient._connect_and_tunnel", new_callable=AsyncMock) as mock_connect:
            await client._handle_http_connect(reader, writer, "example.com:443")
            mock_connect.assert_called_once()
            args = mock_connect.call_args
            assert args[0][2] == "example.com"
            assert args[0][3] == 443


class TestConnectAndTunnel:
    @pytest.mark.asyncio
    async def test_connect_and_tunnel_no_nodes(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        await client._connect_and_tunnel(reader, writer, "example.com", 443)
        # Should try to send error response
        writer.write.assert_called()

    @pytest.mark.asyncio
    async def test_connect_and_tunnel_connection_error(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", side_effect=ConnectionError("refused")):
            # Should not raise, but report fail
            await client._connect_and_tunnel(reader, writer, "example.com", 443)

        # Node should have been failed
        node = client._scheduler.get_node_by_key("10.0.0.1:10080")
        assert node is not None
        assert node.fails >= 1


class TestMopsClientRecovery:
    def test_recovery_loop(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        # Simulate fails
        node = client._scheduler.get_node_by_key("10.0.0.1:10080")
        import time
        node.fails = 2
        node._last_fail = time.monotonic() - 31  # > RECOVERY_INTERVAL

        client._scheduler.recover_nodes()
        assert node.fails == 0

    @pytest.mark.asyncio
    async def test_recovery_loop_task(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        # Start the recovery loop
        task = asyncio.create_task(client._recovery_loop())

        # Let it run briefly
        await asyncio.sleep(0.1)

        # Cancel it
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


class TestHandleProxyExceptions:
    @pytest.mark.asyncio
    async def test_handle_proxy_connection_error(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.read = AsyncMock(side_effect=ConnectionError("reset"))
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await client.handle_proxy(reader, writer)
        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_handle_proxy_os_error(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.read = AsyncMock(side_effect=OSError("network"))
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await client.handle_proxy(reader, writer)
        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_handle_proxy_unexpected_error(self):
        client = MopsClient(listen_port=10081)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.read = AsyncMock(side_effect=ValueError("unexpected"))
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await client.handle_proxy(reader, writer)
        writer.close.assert_called()


class TestSOCKS5ErrorResponses:
    @pytest.mark.asyncio
    async def test_socks5_invalid_version(self):
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
            b"\x04\x01\x00\x01",  # VER=4 (invalid) CMD=1 RSV=0 ATYP=1
            bytes([1, 2, 3, 4]),
            struct.pack("!H", 80),
        ]
        call_count = 0
        async def mock_readexactly(n):
            nonlocal call_count
            result = chunks[call_count]
            call_count += 1
            return result

        reader.readexactly = mock_readexactly

        await client._handle_socks5(reader, writer, b"\x05")
        # Should send error response for invalid version
        writer.write.assert_called()

    @pytest.mark.asyncio
    async def test_socks5_no_available_nodes(self):
        client = MopsClient(listen_port=10081)
        # No nodes added

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
            b"\x05\x01\x00\x01",  # VER=5 CMD=1 RSV=0 ATYP=1
            bytes([1, 2, 3, 4]),
            struct.pack("!H", 80),
        ]
        call_count = 0
        async def mock_readexactly(n):
            nonlocal call_count
            result = chunks[call_count]
            call_count += 1
            return result

        reader.readexactly = mock_readexactly

        await client._handle_socks5(reader, writer, b"\x05")
        # Should try to send error response
        writer.write.assert_called()


class TestConnectAndTunnelWithStats:
    @pytest.mark.asyncio
    async def test_connect_and_tunnel_with_stats(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="127.0.0.1", port=10080))
        client._stats = MagicMock()
        client._stats.active_conns = 0

        # Create mock streams
        client_reader = AsyncMock(spec=asyncio.StreamReader)
        client_writer = AsyncMock(spec=asyncio.StreamWriter)
        client_writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        client_writer.write = MagicMock()
        client_writer.drain = AsyncMock()

        server_reader = AsyncMock(spec=asyncio.StreamReader)
        server_writer = AsyncMock(spec=asyncio.StreamWriter)
        server_writer.write = MagicMock()
        server_writer.drain = AsyncMock()

        with patch("asyncio.open_connection", new_callable=AsyncMock, return_value=(server_reader, server_writer)), \
             patch("mops.client.tunnel", new_callable=AsyncMock):
            await client._connect_and_tunnel(client_reader, client_writer, "example.com", 443)

            # Should have incremented and decremented active_conns
            assert client._stats.active_conns == 0
            # Should have written tunnel header
            server_writer.write.assert_called()


class TestClientStop:
    @pytest.mark.asyncio
    async def test_stop(self):
        client = MopsClient(listen_port=10081)
        client._discovery = MagicMock()
        client._server = AsyncMock()
        await client.stop()
        client._discovery.stop.assert_called_once()
        client._server.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_stop_without_server(self):
        client = MopsClient(listen_port=10081)
        client._discovery = MagicMock()
        client._server = None
        await client.stop()
        client._discovery.stop.assert_called_once()


class TestSOCKS5UnsupportedCmd:
    @pytest.mark.asyncio
    async def test_socks5_bind_command(self):
        client = MopsClient(listen_port=10081)
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        chunks = [
            b"\x01",  # NMETHODS
            b"\x00",  # METHOD
            b"\x05\x02\x00\x01",  # VER=5 CMD=2(BIND) RSV=0 ATYP=1
            bytes([1, 2, 3, 4]),
            struct.pack("!H", 80),
        ]
        call_count = 0

        async def mock_readexactly(n):
            nonlocal call_count
            result = chunks[call_count]
            call_count += 1
            return result

        reader.readexactly = mock_readexactly
        await client._handle_socks5(reader, writer, b"\x05")
        writer.write.assert_called()


class TestConnectAndTunnelOSError:
    @pytest.mark.asyncio
    async def test_connect_and_tunnel_os_error(self):
        from mops.stats import TrafficStats
        client = MopsClient(listen_port=10081, stats=TrafficStats())
        client._scheduler.add_node(NodeInfo(ip="10.0.0.1", port=10080))

        reader = AsyncMock(spec=asyncio.StreamReader)
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", side_effect=OSError("network")):
            await client._connect_and_tunnel(reader, writer, "example.com", 443)

        node = client._scheduler.get_node_by_key("10.0.0.1:10080")
        assert node.fails >= 1

