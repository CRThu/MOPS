"""Traffic statistics collection and status snapshots."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any


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

    def start(self, client_ip: str, target_host: str, target_port: int) -> str:
        with self._lock:
            self._counter += 1
            conn_id = str(self._counter)
            self._active[conn_id] = ConnectionRecord(
                conn_id=conn_id,
                client_ip=client_ip,
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
                    "target_host": r.target_host,
                    "target_port": r.target_port,
                    "status": "active",
                    "started_at": r.started_at,
                })
            for r in self._completed:
                result.append({
                    "conn_id": r.conn_id,
                    "client_ip": r.client_ip,
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
