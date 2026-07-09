"""Node registry for tracking discovered nodes (dashboard side)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from ..protocol import NODE_HISTORY_TTL


@dataclass
class NodeRecord:
    ip: str
    port: int
    api_port: int
    hostname: str
    first_seen: float
    last_seen: float


class NodeRegistry:
    """Track all discovered nodes, retain offline nodes for TTL duration.

    Thread-safe via Lock (zeroconf callbacks run on a background thread).
    """

    def __init__(self, ttl: int = NODE_HISTORY_TTL) -> None:
        self._nodes: dict[str, NodeRecord] = {}
        self._ttl = ttl
        self._lock = threading.Lock()

    def record_seen(self, ip: str, port: int, api_port: int, hostname: str) -> None:
        key = f"{ip}:{port}"
        now = time.monotonic()
        with self._lock:
            if key in self._nodes:
                self._nodes[key].last_seen = now
                self._nodes[key].api_port = api_port
                self._nodes[key].hostname = hostname
            else:
                self._nodes[key] = NodeRecord(
                    ip=ip, port=port, api_port=api_port,
                    hostname=hostname, first_seen=now, last_seen=now,
                )

    def mark_offline(self, ip: str, port: int) -> None:
        key = f"{ip}:{port}"
        with self._lock:
            if key in self._nodes:
                self._nodes[key].last_seen = 0  # mark as offline

    def get_all(self) -> dict[str, NodeRecord]:
        with self._lock:
            return dict(self._nodes)

    def prune(self) -> None:
        now = time.monotonic()
        with self._lock:
            expired = [
                k for k, v in self._nodes.items()
                if v.last_seen == 0 and (now - v.first_seen) > self._ttl
            ]
            for k in expired:
                del self._nodes[k]
