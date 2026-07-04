"""Bidirectional async traffic pipe (shared by Server and Client)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from .protocol import BUFFER_SIZE

if TYPE_CHECKING:
    from .stats import TrafficStats


async def pipe(
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
    stats: TrafficStats | None = None,
    node_name: str = "",
    direction: str = "up",
) -> None:
    """Read from reader, write to writer, optionally record traffic stats."""
    try:
        while True:
            chunk = await reader.read(BUFFER_SIZE)
            if not chunk:
                break
            if stats and node_name:
                if direction == "up":
                    stats.record_upload(node_name, len(chunk))
                else:
                    stats.record_download(node_name, len(chunk))
            writer.write(chunk)
            await writer.drain()
    except (asyncio.IncompleteReadError, ConnectionError, OSError):
        pass
    except asyncio.CancelledError:
        pass


async def tunnel(
    r1: asyncio.StreamReader,
    w1: asyncio.StreamWriter,
    r2: asyncio.StreamReader,
    w2: asyncio.StreamWriter,
    stats: TrafficStats | None = None,
    node_name: str = "",
) -> None:
    """Bidirectional copy between two (reader, writer) pairs.

    Returns when either direction closes or errors.
    """
    try:
        await asyncio.gather(
            pipe(r1, w2, stats, node_name, direction="down"),
            pipe(r2, w1, stats, node_name, direction="up"),
        )
    except Exception:
        pass
