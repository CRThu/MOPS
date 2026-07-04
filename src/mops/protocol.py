"""Shared protocol constants for MOPS."""

from pathlib import Path

MOPS_SERVICE_TYPE = "_mops-proxy._tcp.local."
DEFAULT_BASE_PORT = 10080
BUFFER_SIZE = 65536
MAX_FAILS = 2
RECOVERY_INTERVAL = 30  # seconds
MDNS_TTL = 60  # seconds
STRATEGY_RANDOM = "random"
STRATEGY_HASH = "hash"
LOG_DIR = Path.home() / ".mops" / "logs"
