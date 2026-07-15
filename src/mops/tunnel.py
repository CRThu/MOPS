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
    tag: str = "",
) -> str:
    """Read from reader, write to writer, optionally record traffic stats.

    Returns a close reason string: "eof", "error:<detail>", or "cancelled".
    """
    try:
        while True:
            chunk = await reader.read(BUFFER_SIZE)
            if not chunk:
                return "eof"
            if stats and node_name:
                if direction == "up":
                    stats.record_upload(node_name, len(chunk))
                else:
                    stats.record_download(node_name, len(chunk))
            writer.write(chunk)
            await writer.drain()
    except asyncio.CancelledError:
        return "cancelled"
    except asyncio.IncompleteReadError as e:
        reason = f"incomplete-read ({len(e.partial)} bytes received)"
        logger.debug(f"Pipe {tag} {direction}: {reason}")
        return f"error:{reason}"
    except RuntimeError as e:
        # drain() can raise RuntimeError if writer is closing
        logger.debug(f"Pipe {tag} {direction}: runtime error: {e}")
        return f"error:{e}"
    except (ConnectionError, OSError) as e:
        errno = getattr(e, "errno", None)
        winerror = getattr(e, "winerror", None)
        # WinError 10054 = connection reset by peer (normal for HTTPS close)
        # WinError 121 = semaphore timeout (real connectivity issue)
        # WinError 1225 = remote computer refused connection
        # errno 11004 = DNS resolution failed
        if winerror in (10054,):
            logger.debug(f"Pipe {tag} {direction}: connection reset (normal)")
            return "error:connection-reset"
        if winerror == 121:
            logger.warning(f"Pipe {tag} {direction}: connection timeout")
            return "error:timeout"
        if winerror == 1225:
            logger.warning(f"Pipe {tag} {direction}: connection refused")
            return "error:connection-refused"
        if errno == 11004:
            logger.warning(f"Pipe {tag} {direction}: DNS resolution failed")
            return "error:dns-failed"
        logger.debug(f"Pipe {tag} {direction}: {e}")
        return f"error:{e}"


async def tunnel(
    r1: asyncio.StreamReader,
    w1: asyncio.StreamWriter,
    r2: asyncio.StreamReader,
    w2: asyncio.StreamWriter,
    stats: TrafficStats | None = None,
    node_name: str = "",
    tag: str = "",
) -> str:
    """Bidirectional copy between two (reader, writer) pairs.

    Returns when either direction closes or errors.
    Returns a combined close reason.
    """
    try:
        results = await asyncio.gather(
            pipe(r1, w2, stats, node_name, direction="down", tag=tag),
            pipe(r2, w1, stats, node_name, direction="up", tag=tag),
        )
        # Return the first non-eof reason, or "eof" if both closed cleanly
        for r in results:
            if r != "eof":
                return r
        return "eof"
    except asyncio.CancelledError:
        return "cancelled"
    except (ConnectionError, OSError) as e:
        logger.debug(f"Tunnel {tag}: {e}")
        return f"error:{e}"
