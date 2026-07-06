"""Shared protocol constants for MOPS."""

from pathlib import Path

MOPS_SERVICE_TYPE = "_mops-proxy._tcp.local."
DEFAULT_BASE_PORT = 10080
BUFFER_SIZE = 65536
MAX_FAILS = 2
RECOVERY_INTERVAL = 30  # seconds
MDNS_TTL = 60  # seconds
NODE_HISTORY_TTL = 3600  # 1 hour: keep offline nodes in registry
SPEED_WINDOW = 5  # seconds: ring buffer capacity for speed calculation
STRATEGY_RANDOM = "random"
STRATEGY_HASH = "hash"
LOG_DIR = Path.home() / ".mops" / "logs"
