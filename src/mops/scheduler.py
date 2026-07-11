"""Load balancer scheduler with circuit breaker."""

from __future__ import annotations

import random
import time

from loguru import logger

from .protocol import MAX_FAILS, RECOVERY_INTERVAL, STRATEGY_HASH, STRATEGY_RANDOM, NodeInfo


class NoAvailableNodeError(Exception):
    """Raised when no nodes are available for selection."""


class Scheduler:
    """Load balancer with random/hash strategies and circuit breaker."""

    def __init__(self, strategy: str = STRATEGY_RANDOM) -> None:
        self.strategy = strategy
        self._nodes: dict[str, NodeInfo] = {}
        self._recovery_time: dict[str, float] = {}

    def add_node(self, node: NodeInfo) -> None:
        key = f"{node.ip}:{node.port}"
        if key in self._nodes:
            logger.debug(f"Node updated: {key}")
        else:
            logger.info(f"Node added: {key}")
        self._nodes[key] = node
        # Clear recovery time if node is re-added
        self._recovery_time.pop(key, None)

    def remove_node(self, key: str) -> None:
        if key in self._nodes:
            logger.info(f"Node removed: {key}")
            del self._nodes[key]
        self._recovery_time.pop(key, None)

    def remove_by_name(self, name: str) -> None:
        for key, node in list(self._nodes.items()):
            if node.name == name:
                self.remove_node(key)
                return

    def report_fail(self, node: NodeInfo) -> None:
        key = f"{node.ip}:{node.port}"
        if key not in self._nodes:
            return
        self._nodes[key].fails += 1
        self._nodes[key].last_fail = time.monotonic()
        logger.warning(
            f"Node fail reported: {key} (fails={self._nodes[key].fails})"
        )

    def recover_nodes(self) -> None:
        now = time.monotonic()
        for key, node in list(self._nodes.items()):
            if node.fails >= MAX_FAILS:
                last_fail = node.last_fail
                if now - last_fail >= RECOVERY_INTERVAL:
                    node.fails = 0
                    logger.info(f"Node recovered: {key}")

    def select(self, client_ip: str = "", target_host: str = "") -> NodeInfo:
        active = self.get_active_nodes()
        if not active:
            raise NoAvailableNodeError("No available nodes")

        if self.strategy == STRATEGY_HASH:
            if not client_ip or not target_host:
                # Fallback to random if hash params missing
                return random.choice(active)
            idx = hash(f"{client_ip}:{target_host}") % len(active)
            return active[idx]
        else:
            # random strategy (default)
            return random.choice(active)

    def get_active_nodes(self) -> list[NodeInfo]:
        return [n for n in self._nodes.values() if n.fails < MAX_FAILS]

    def get_all_nodes(self) -> list[NodeInfo]:
        return list(self._nodes.values())

    def get_node_by_key(self, key: str) -> NodeInfo | None:
        return self._nodes.get(key)
