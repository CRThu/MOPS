"""Additional tunnel tests for exception paths."""

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


class TestPipeExceptions:
    @pytest.mark.asyncio
    async def test_pipe_connection_error(self):
        reader = AsyncMockRead(raise_on_read=ConnectionError("reset"))
        writer = AsyncMockWrite()

        # Should not raise
        await pipe(reader, writer)
        assert writer.written == b""

    @pytest.mark.asyncio
    async def test_pipe_os_error(self):
        reader = AsyncMockRead(raise_on_read=OSError("network"))
        writer = AsyncMockWrite()

        await pipe(reader, writer)
        assert writer.written == b""

    @pytest.mark.asyncio
    async def test_pipe_incomplete_read(self):
        reader = AsyncMockRead(raise_on_read=asyncio.IncompleteReadError(b"", 10))
        writer = AsyncMockWrite()

        await pipe(reader, writer)
        assert writer.written == b""

    @pytest.mark.asyncio
    async def test_pipe_cancelled(self):
        reader = AsyncMockRead(raise_on_read=asyncio.CancelledError())
        writer = AsyncMockWrite()

        await pipe(reader, writer)
        assert writer.written == b""


class TestTunnelExceptions:
    @pytest.mark.asyncio
    async def test_tunnel_with_exception_in_pipe(self):
        r1 = AsyncMockRead(raise_on_read=ConnectionError("fail"))
        w1 = AsyncMockWrite()
        r2 = AsyncMockRead(b"data")
        w2 = AsyncMockWrite()

        # Should not raise
        await asyncio.wait_for(tunnel(r1, w1, r2, w2), timeout=2.0)

    @pytest.mark.asyncio
    async def test_tunnel_both_sides_error(self):
        r1 = AsyncMockRead(raise_on_read=ConnectionError("fail1"))
        w1 = AsyncMockWrite()
        r2 = AsyncMockRead(raise_on_read=ConnectionError("fail2"))
        w2 = AsyncMockWrite()

        await asyncio.wait_for(tunnel(r1, w1, r2, w2), timeout=2.0)
