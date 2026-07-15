"""Additional tunnel tests for exception paths and return values."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from mops.tunnel import pipe, tunnel
from mops.stats import TrafficStats


class AsyncMockRead:
    def __init__(self, data: bytes = b"", raise_on_read: Exception = None):
        self._data = data
        self._pos = 0
        self._raise = raise_on_read

    async def read(self, n: int = -1) -> bytes:
        if self._raise:
            raise self._raise
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
    def __init__(self):
        self.written = b""
        self.closed = False

    def write(self, data):
        self.written += data

    async def drain(self):
        pass

    def close(self):
        self.closed = True

    async def wait_closed(self):
        pass


class TestPipeReturnValues:
    """Test that pipe() returns correct close reason strings."""

    @pytest.mark.asyncio
    async def test_pipe_eof_returns_eof(self):
        reader = AsyncMockRead(b"hello")
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert result == "eof"
        assert writer.written == b"hello"

    @pytest.mark.asyncio
    async def test_pipe_empty_returns_eof(self):
        reader = AsyncMockRead(b"")
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert result == "eof"

    @pytest.mark.asyncio
    async def test_pipe_connection_error_returns_error(self):
        reader = AsyncMockRead(raise_on_read=ConnectionError("reset"))
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert result.startswith("error:")

    @pytest.mark.asyncio
    async def test_pipe_os_error_returns_error(self):
        reader = AsyncMockRead(raise_on_read=OSError("network"))
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert result.startswith("error:")

    @pytest.mark.asyncio
    async def test_pipe_incomplete_read_returns_error(self):
        reader = AsyncMockRead(raise_on_read=asyncio.IncompleteReadError(b"", 10))
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert result.startswith("error:")
        assert "incomplete-read" in result

    @pytest.mark.asyncio
    async def test_pipe_cancelled_returns_cancelled(self):
        reader = AsyncMockRead(raise_on_read=asyncio.CancelledError())
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert result == "cancelled"


class TestPipeWinErrorClassification:
    """Test that specific Windows error codes are classified correctly."""

    @pytest.mark.asyncio
    async def test_pipe_winerror_10054_connection_reset(self):
        """WinError 10054 = connection reset by peer (normal for HTTPS close)."""
        exc = ConnectionError("reset")
        exc.winerror = 10054
        reader = AsyncMockRead(raise_on_read=exc)
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert "connection-reset" in result

    @pytest.mark.asyncio
    async def test_pipe_winerror_121_timeout(self):
        """WinError 121 = semaphore timeout (real connectivity issue)."""
        exc = OSError("timeout")
        exc.winerror = 121
        reader = AsyncMockRead(raise_on_read=exc)
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert "timeout" in result

    @pytest.mark.asyncio
    async def test_pipe_winerror_1225_refused(self):
        """WinError 1225 = remote computer refused connection."""
        exc = ConnectionError("refused")
        exc.winerror = 1225
        reader = AsyncMockRead(raise_on_read=exc)
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert "connection-refused" in result

    @pytest.mark.asyncio
    async def test_pipe_errno_11004_dns_failed(self):
        """errno 11004 = DNS resolution failed."""
        exc = OSError("dns")
        exc.errno = 11004
        exc.winerror = None
        reader = AsyncMockRead(raise_on_read=exc)
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert "dns-failed" in result

    @pytest.mark.asyncio
    async def test_pipe_generic_os_error(self):
        """Generic OSError without specific code."""
        exc = OSError("generic error")
        exc.errno = None
        exc.winerror = None
        reader = AsyncMockRead(raise_on_read=exc)
        writer = AsyncMockWrite()
        result = await pipe(reader, writer)
        assert result.startswith("error:")


class TestPipeStatsRecording:
    """Test that pipe() records traffic stats correctly."""

    @pytest.mark.asyncio
    async def test_pipe_records_upload(self):
        stats = TrafficStats()
        reader = AsyncMockRead(b"hello")
        writer = AsyncMockWrite()
        await pipe(reader, writer, stats=stats, node_name="test:80", direction="up")
        assert stats.get_total_up() == 5

    @pytest.mark.asyncio
    async def test_pipe_records_download(self):
        stats = TrafficStats()
        reader = AsyncMockRead(b"hello")
        writer = AsyncMockWrite()
        await pipe(reader, writer, stats=stats, node_name="test:80", direction="down")
        assert stats.get_total_down() == 5

    @pytest.mark.asyncio
    async def test_pipe_no_stats_when_none(self):
        reader = AsyncMockRead(b"hello")
        writer = AsyncMockWrite()
        # Should not raise even without stats
        await pipe(reader, writer, stats=None, node_name="test:80")


class TestTunnelReturnValues:
    """Test that tunnel() returns correct close reason strings."""

    @pytest.mark.asyncio
    async def test_tunnel_both_eof_returns_eof(self):
        r1 = AsyncMockRead(b"data")
        w1 = AsyncMockWrite()
        r2 = AsyncMockRead(b"data")
        w2 = AsyncMockWrite()
        result = await asyncio.wait_for(tunnel(r1, w1, r2, w2), timeout=2.0)
        assert result == "eof"

    @pytest.mark.asyncio
    async def test_tunnel_one_side_error_returns_error(self):
        r1 = AsyncMockRead(raise_on_read=ConnectionError("fail"))
        w1 = AsyncMockWrite()
        r2 = AsyncMockRead(b"data")
        w2 = AsyncMockWrite()
        result = await asyncio.wait_for(tunnel(r1, w1, r2, w2), timeout=2.0)
        assert result.startswith("error:")

    @pytest.mark.asyncio
    async def test_tunnel_both_sides_error(self):
        r1 = AsyncMockRead(raise_on_read=ConnectionError("fail1"))
        w1 = AsyncMockWrite()
        r2 = AsyncMockRead(raise_on_read=ConnectionError("fail2"))
        w2 = AsyncMockWrite()
        result = await asyncio.wait_for(tunnel(r1, w1, r2, w2), timeout=2.0)
        assert result.startswith("error:")

    @pytest.mark.asyncio
    async def test_tunnel_with_tag(self):
        r1 = AsyncMockRead(b"data")
        w1 = AsyncMockWrite()
        r2 = AsyncMockRead(b"")
        w2 = AsyncMockWrite()
        # Tag is passed through but doesn't affect return value
        result = await asyncio.wait_for(
            tunnel(r1, w1, r2, w2, tag="test-tag"), timeout=2.0
        )
        assert result == "eof"

    @pytest.mark.asyncio
    async def test_tunnel_with_stats(self):
        stats = TrafficStats()
        r1 = AsyncMockRead(b"hello")
        w1 = AsyncMockWrite()
        r2 = AsyncMockRead(b"world")
        w2 = AsyncMockWrite()
        result = await asyncio.wait_for(
            tunnel(r1, w1, r2, w2, stats=stats, node_name="test:80"), timeout=2.0
        )
        assert result == "eof"
        assert stats.get_total_up() == 5
        assert stats.get_total_down() == 5
