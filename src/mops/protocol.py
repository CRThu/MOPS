"""Shared protocol constants for MOPS."""

from __future__ import annotations

import json
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

PROTOCOL_VERSION = 1


def build_header(host: str, port: int, client_port: int = 0, client_host: str = "") -> bytes:
    """Build a JSON tunnel header line.

    Format: {"version":1,"host":"example.com:443","client_port":10090,"client_host":"Carrot-PC"}\\n
    """
    h: dict[str, int | str] = {"version": PROTOCOL_VERSION, "host": f"{host}:{port}"}
    if client_port:
        h["client_port"] = client_port
    if client_host:
        h["client_host"] = client_host
    return json.dumps(h, separators=(",", ":")).encode() + b"\n"


def parse_header(raw: bytes) -> tuple[str, int, int, str]:
    """Parse a tunnel header line. Returns (host, port, client_port, client_host).

    Format: {"version":1,"host":"example.com:443","client_port":10090,"client_host":"Carrot-PC"}
    """
    line = raw.decode().strip()
    if not line:
        raise ValueError("empty header")

    if not line.startswith("{"):
        raise ValueError(f"invalid header format: {line[:60]!r}")

    h = json.loads(line)
    host_port = h["host"]
    host, port_str = host_port.rsplit(":", 1)
    return host, int(port_str), int(h.get("client_port", 0)), h.get("client_host", "")
