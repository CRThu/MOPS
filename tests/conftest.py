"""Shared test fixtures for MOPS test suite."""

from __future__ import annotations

import asyncio
import socket
import tempfile
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest


def _free_port() -> int:
    """Find a free TCP port on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def free_port() -> int:
    """Return a free TCP port number."""
    return _free_port()


@pytest.fixture
def mock_zeroconf():
    """Mock zeroconf.Zeroconf instance."""
    zc = MagicMock()
    zc.register_service = AsyncMock()
    zc.unregister_service = AsyncMock()
    zc.close = MagicMock()
    return zc


@pytest.fixture
def mock_service_info():
    """Mock zeroconf.ServiceInfo."""
    info = MagicMock()
    info.name = "mops-server-1-10080._mops-proxy._tcp.local."
    info.type = "_mops-proxy._tcp.local."
    info.port = 10080
    info.properties = {b"weight": b"1", b"version": b"0.1.0"}
    info.parsed_addresses.return_value = ["192.168.1.100"]
    return info


@pytest.fixture
async def echo_server() -> AsyncIterator[tuple[str, int]]:
    """Start a simple TCP echo server, yield (host, port), then shut down."""
    data_received = asyncio.Event()
    received_chunks: list[bytes] = []

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            while True:
                chunk = await reader.read(65536)
                if not chunk:
                    break
                received_chunks.append(chunk)
                writer.write(chunk)
                await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()
            data_received.set()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    yield addr[0], addr[1]
    server.close()
    await server.wait_closed()


@pytest.fixture
async def http_echo_server() -> AsyncIterator[tuple[str, int]]:
    """Start a simple HTTP echo server, yield (host, port), then shut down."""

    async def handle_client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        try:
            data = await reader.readuntil(b"\r\n\r\n")
            body = b"HTTP/1.1 200 OK\r\nContent-Length: 2\r\n\r\nOK"
            writer.write(body)
            await writer.drain()
        except (ConnectionError, asyncio.IncompleteReadError):
            pass
        finally:
            writer.close()
            await writer.wait_closed()

    server = await asyncio.start_server(handle_client, "127.0.0.1", 0)
    addr = server.sockets[0].getsockname()
    yield addr[0], addr[1]
    server.close()
    await server.wait_closed()


@pytest.fixture
def make_mock_streams():
    """Factory fixture to create mock StreamReader/StreamWriter pairs."""
    from io import BytesIO

    def _make(data: bytes = b"") -> tuple[AsyncMock, AsyncMock]:
        reader = AsyncMock(spec=asyncio.StreamReader)
        reader.read = AsyncMock(return_value=data)
        reader.readexactly = AsyncMock(return_value=data)
        reader.readuntil = AsyncMock(return_value=data)
        reader.readline = AsyncMock(return_value=data)
        reader.at_eof = AsyncMock(return_value=not bool(data))

        writer = AsyncMock(spec=asyncio.StreamWriter)
        writer.write = MagicMock()
        writer.drain = AsyncMock()
        writer.close = MagicMock()
        writer.wait_closed = AsyncMock()
        writer.get_extra_info = MagicMock(return_value=("127.0.0.1", 12345))

        return reader, writer

    return _make
