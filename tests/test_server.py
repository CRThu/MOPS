"""Tests for MopsServer: relay logic, mDNS broadcast, target parsing."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mops.server import MdnsBroadcaster, MopsServer
from mops.protocol import build_header


class TestMopsServer:
    """Test TCP relay server logic."""

    @pytest.mark.asyncio
    async def test_handle_client_invalid_header(self):
        server = MopsServer(port=10080)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=b"invalid\n")
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await server.handle_client(reader, writer)
        writer.close.assert_called()
        writer.wait_closed.assert_called()

    @pytest.mark.asyncio
    async def test_handle_client_empty_header(self):
        server = MopsServer(port=10080)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=b"")
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        await server.handle_client(reader, writer)
        writer.close.assert_called()
        writer.wait_closed.assert_called()

    @pytest.mark.asyncio
    async def test_handle_client_connection_error(self):
        server = MopsServer(port=10080)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=build_header("example.com", 80))
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        with patch("asyncio.open_connection", side_effect=ConnectionError("refused")):
            await server.handle_client(reader, writer)

        writer.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_client_success(self):
        server = MopsServer(port=10080)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=build_header("example.com", 80))

        target_reader = AsyncMock(spec=asyncio.StreamReader)
        target_writer = AsyncMock(spec=asyncio.StreamWriter)
        target_writer.close = MagicMock()
        target_writer.wait_closed = AsyncMock()

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.write = MagicMock()
        writer.drain = AsyncMock()

        with patch(
            "asyncio.open_connection",
            new_callable=AsyncMock,
            return_value=(target_reader, target_writer),
        ), patch("mops.server.tunnel", new_callable=AsyncMock) as mock_tunnel:
            await server.handle_client(reader, writer)
            mock_tunnel.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_client_incomplete_read(self):
        from mops.stats import ConnectionTracker
        server = MopsServer(port=10080, conn_tracker=ConnectionTracker())
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=build_header("example.com", 80))
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", side_effect=asyncio.IncompleteReadError(b"", 10)):
            await server.handle_client(reader, writer)
        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_handle_client_unexpected_error(self):
        server = MopsServer(port=10080)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=build_header("example.com", 80))
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch("asyncio.open_connection", side_effect=RuntimeError("unexpected")):
            await server.handle_client(reader, writer)
        writer.close.assert_called()

    @pytest.mark.asyncio
    async def test_handle_client_wait_closed_runtime_error(self):
        server = MopsServer(port=10080)
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=build_header("example.com", 80))
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock(side_effect=RuntimeError("already closed"))

        with patch("asyncio.open_connection", side_effect=ConnectionError("refused")):
            await server.handle_client(reader, writer)
        writer.close.assert_called()


class TestMdnsBroadcaster:
    """Test mDNS registration/unregistration."""

    @pytest.mark.asyncio
    async def test_register_unregister(self):
        broadcaster = MdnsBroadcaster()
        with patch("mops.server.Zeroconf") as mock_zc_cls, \
             patch("mops.server.ServiceInfo") as mock_si_cls:
            mock_zc = AsyncMock()
            mock_zc.async_register_service = AsyncMock()
            mock_zc.async_unregister_service = AsyncMock()
            mock_zc.close = MagicMock()
            mock_zc_cls.return_value = mock_zc

            mock_si = MagicMock()
            mock_si_cls.return_value = mock_si

            await broadcaster.register(port=10080, weight=1, ttl=60)
            mock_zc.async_register_service.assert_called_once_with(mock_si)

            await broadcaster.unregister()
            mock_zc.async_unregister_service.assert_called_once()
            mock_zc.close.assert_called_once()

    @pytest.mark.asyncio
    async def test_unregister_without_register(self):
        broadcaster = MdnsBroadcaster()
        # Should not raise
        await broadcaster.unregister()


class TestServerErrorTracking:
    """Test server error tracking with ConnectionTracker."""

    @pytest.mark.asyncio
    async def test_handle_client_records_error_on_connect_timeout(self):
        from mops.stats import ConnectionTracker
        tracker = ConnectionTracker()
        server = MopsServer(port=10080, conn_tracker=tracker)

        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=build_header("example.com", 443))
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        # Simulate connection timeout
        with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError()):
            await server.handle_client(reader, writer)

        # Should have recorded an error
        assert tracker.active_count() == 0
        conns = tracker.get_connections()
        assert len(conns) == 1
        assert conns[0]["status"] == "error"
        assert "timeout" in conns[0]["error_reason"]

    @pytest.mark.asyncio
    async def test_handle_client_records_error_on_connect_refused(self):
        from mops.stats import ConnectionTracker
        tracker = ConnectionTracker()
        server = MopsServer(port=10080, conn_tracker=tracker)

        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=build_header("example.com", 443))
        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch("asyncio.wait_for", side_effect=ConnectionError("refused")):
            await server.handle_client(reader, writer)

        conns = tracker.get_connections()
        assert len(conns) == 1
        assert conns[0]["status"] == "error"
        assert "connect-failed" in conns[0]["error_reason"]

    @pytest.mark.asyncio
    async def test_handle_client_records_error_on_tunnel_close(self):
        from mops.stats import ConnectionTracker
        tracker = ConnectionTracker()
        server = MopsServer(port=10080, conn_tracker=tracker)

        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=build_header("example.com", 443))

        target_reader = AsyncMock(spec=asyncio.StreamReader)
        target_writer = AsyncMock(spec=asyncio.StreamWriter)
        target_writer.close = MagicMock()
        target_writer.wait_closed = AsyncMock()

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(target_reader, target_writer)), \
             patch("mops.server.tunnel", new_callable=AsyncMock, return_value="error:timeout"):
            await server.handle_client(reader, writer)

        conns = tracker.get_connections()
        assert len(conns) == 1
        assert conns[0]["status"] == "error"
        assert "timeout" in conns[0]["error_reason"]

    @pytest.mark.asyncio
    async def test_handle_client_records_success(self):
        from mops.stats import ConnectionTracker
        tracker = ConnectionTracker()
        server = MopsServer(port=10080, conn_tracker=tracker)

        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.readline = AsyncMock(return_value=build_header("example.com", 443))

        target_reader = AsyncMock(spec=asyncio.StreamReader)
        target_writer = AsyncMock(spec=asyncio.StreamWriter)
        target_writer.close = MagicMock()
        target_writer.wait_closed = AsyncMock()

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()

        with patch("asyncio.wait_for", new_callable=AsyncMock, return_value=(target_reader, target_writer)), \
             patch("mops.server.tunnel", new_callable=AsyncMock, return_value="eof"):
            await server.handle_client(reader, writer)

        conns = tracker.get_connections()
        assert len(conns) == 1
        assert conns[0]["status"] == "completed"
        assert conns[0]["error_reason"] == ""


class TestServerMdnsBroadcasterDetectLanIp:
    """Test _detect_lan_ip fallback behavior."""

    def test_detect_lan_ip_logs_warning_on_fallback(self):
        """When no LAN IP is detected, a warning should be logged."""
        import socket
        from mops.server import MdnsBroadcaster
        # Mock both detection methods to fail
        with patch("socket.socket") as mock_socket_cls:
            mock_sock = MagicMock()
            mock_sock.connect.side_effect = OSError("no route")
            mock_sock.close = MagicMock()
            mock_socket_cls.return_value = mock_sock

            with patch("socket.getaddrinfo", side_effect=OSError("no interfaces")):
                result = MdnsBroadcaster._detect_lan_ip()
                # Should fallback to 127.0.0.1
                assert len(result) == 1
                assert result[0] == socket.inet_aton("127.0.0.1")
