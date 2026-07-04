"""Traffic statistics collection and status snapshots."""

from __future__ import annotations

import time
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
