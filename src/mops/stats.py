"""Traffic statistics collection and status snapshots."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .protocol import NODE_HISTORY_TTL, SPEED_WINDOW


@dataclass
class NodeStats:
    ip: str
    port: int
    fails: int = 0
    up: int = 0
    down: int = 0


@dataclass
class StatusSnapshot:
    mode: str
    strategy: str
    server_host: str
    server_port: int
    client_listen: str
    client_port: int
    api_port: int
    nodes: list[dict[str, Any]]
    total_up: int = 0
    total_down: int = 0
    active_conns: int = 0
    uptime: float = 0.0


class TrafficStats:
    def __init__(self) -> None:
        self._start_time = time.monotonic()
        self._node_stats: dict[str, NodeStats] = {}
        self.active_conns: int = 0

    def record_upload(self, node_name: str, byte_count: int) -> None:
        if node_name not in self._node_stats:
            self._node_stats[node_name] = NodeStats(
                ip=node_name.split(":")[0],
                port=int(node_name.split(":")[1]) if ":" in node_name else 0,
            )
        self._node_stats[node_name].up += byte_count

    def record_download(self, node_name: str, byte_count: int) -> None:
        if node_name not in self._node_stats:
            self._node_stats[node_name] = NodeStats(
                ip=node_name.split(":")[0],
                port=int(node_name.split(":")[1]) if ":" in node_name else 0,
            )
        self._node_stats[node_name].down += byte_count

    def update_node_fails(self, node_name: str, fails: int) -> None:
        if node_name in self._node_stats:
            self._node_stats[node_name].fails = fails

    def get_node_stats(self, node_name: str) -> NodeStats | None:
        return self._node_stats.get(node_name)

    def get_all_nodes(self) -> dict[str, NodeStats]:
        return dict(self._node_stats)

    def get_uptime(self) -> float:
        return time.monotonic() - self._start_time

    def get_total_up(self) -> int:
        return sum(n.up for n in self._node_stats.values())

    def get_total_down(self) -> int:
        return sum(n.down for n in self._node_stats.values())

    def get_snapshot(
        self,
        mode: str = "both",
        strategy: str = "random",
        server_host: str = "0.0.0.0",
        server_port: int = 10080,
        client_listen: str = "127.0.0.1",
        client_port: int = 10081,
        api_port: int = 10082,
    ) -> StatusSnapshot:
        nodes = []
        for name, ns in self._node_stats.items():
            nodes.append({
                "ip": ns.ip,
                "port": ns.port,
                "fails": ns.fails,
                "up": ns.up,
                "down": ns.down,
            })
        return StatusSnapshot(
            mode=mode,
            strategy=strategy,
            server_host=server_host,
            server_port=server_port,
            client_listen=client_listen,
            client_port=client_port,
            api_port=api_port,
            nodes=nodes,
            total_up=self.get_total_up(),
            total_down=self.get_total_down(),
            active_conns=self.active_conns,
            uptime=self.get_uptime(),
        )


@dataclass
class ConnectionRecord:
    conn_id: str
    client_ip: str
    client_port: int
    client_host: str
    target_host: str
    target_port: int
    status: str  # "active" | "completed"
    started_at: float  # time.monotonic()
    ended_at: float | None = None


class ConnectionTracker:
    """Tracks per-connection info on the server side.

    Maintains active connections and a rolling window of completed ones.
    Thread-safe via Lock.
    """

    def __init__(self, history_minutes: int = 5) -> None:
        self._history_minutes = history_minutes
        self._active: dict[str, ConnectionRecord] = {}
        self._completed: deque[ConnectionRecord] = deque()
        self._lock = threading.Lock()
        self._counter = 0

    def start(self, client_ip: str, target_host: str, target_port: int, client_port: int = 0, client_host: str = "") -> str:
        with self._lock:
            self._counter += 1
            conn_id = str(self._counter)
            self._active[conn_id] = ConnectionRecord(
                conn_id=conn_id,
                client_ip=client_ip,
                client_port=client_port,
                client_host=client_host,
                target_host=target_host,
                target_port=target_port,
                status="active",
                started_at=time.monotonic(),
            )
            return conn_id

    def end(self, conn_id: str) -> None:
        with self._lock:
            rec = self._active.pop(conn_id, None)
            if rec:
                rec.status = "completed"
                rec.ended_at = time.monotonic()
                self._completed.append(rec)
            self._prune()

    def get_connections(self) -> list[dict]:
        with self._lock:
            self._prune()
            result: list[dict] = []
            for r in self._active.values():
                result.append({
                    "conn_id": r.conn_id,
                    "client_ip": r.client_ip,
                    "client_port": r.client_port,
                    "client_host": r.client_host,
                    "target_host": r.target_host,
                    "target_port": r.target_port,
                    "status": "active",
                    "started_at": r.started_at,
                })
            for r in self._completed:
                result.append({
                    "conn_id": r.conn_id,
                    "client_ip": r.client_ip,
                    "client_port": r.client_port,
                    "client_host": r.client_host,
                    "target_host": r.target_host,
                    "target_port": r.target_port,
                    "status": "completed",
                    "started_at": r.started_at,
                    "ended_at": r.ended_at,
                })
            return result

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def _prune(self) -> None:
        cutoff = time.monotonic() - self._history_minutes * 60
        while self._completed and self._completed[0].ended_at is not None and self._completed[0].ended_at < cutoff:
            self._completed.popleft()


@dataclass
class NodeRecord:
    ip: str
    port: int
    api_port: int
    hostname: str
    first_seen: float
    last_seen: float


class NodeRegistry:
    """Track all discovered nodes, retain offline nodes for TTL duration."""

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


class TrafficHistory:
    """Ring buffer for computing real-time speed from total counters."""

    def __init__(self, capacity: int = SPEED_WINDOW) -> None:
        self._samples: deque = deque(maxlen=capacity)

    def record(self, total_up: int, total_down: int, active_conns: int) -> None:
        self._samples.append({
            "t": time.monotonic(),
            "up": total_up,
            "down": total_down,
            "conns": active_conns,
        })

    def compute_speed(self) -> tuple[int, int]:
        """Return (speed_up, speed_down) in bytes/sec."""
        if len(self._samples) < 2:
            return (0, 0)
        a, b = self._samples[-2], self._samples[-1]
        dt = b["t"] - a["t"]
        if dt <= 0:
            return (0, 0)
        return (
            int((b["up"] - a["up"]) / dt),
            int((b["down"] - a["down"]) / dt),
        )
