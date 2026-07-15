"""Connection lifecycle tracking (server side)."""

from __future__ import annotations

import threading
import time
from collections import deque
from dataclasses import dataclass


@dataclass
class ConnectionRecord:
    conn_id: str
    client_ip: str
    client_port: int
    client_host: str
    target_host: str
    target_port: int
    status: str  # "active" | "completed" | "error"
    started_at: float  # time.monotonic()
    ended_at: float | None = None
    error_reason: str = ""


class ConnectionTracker:
    """Tracks per-connection info on the server side.

    Maintains active connections and a rolling window of completed ones.
    Thread-safe via Lock (zeroconf callbacks run on a background thread).
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

    def end(self, conn_id: str, error_reason: str = "") -> None:
        with self._lock:
            rec = self._active.pop(conn_id, None)
            if rec:
                rec.ended_at = time.monotonic()
                if error_reason:
                    rec.status = "error"
                    rec.error_reason = error_reason
                else:
                    rec.status = "completed"
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
                    "status": r.status,
                    "started_at": r.started_at,
                    "ended_at": r.ended_at,
                    "error_reason": r.error_reason,
                })
            return result

    def active_count(self) -> int:
        with self._lock:
            return len(self._active)

    def _prune(self) -> None:
        cutoff = time.monotonic() - self._history_minutes * 60
        while self._completed:
            rec = self._completed[0]
            if rec.ended_at is None or rec.ended_at >= cutoff:
                break
            self._completed.popleft()
