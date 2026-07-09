"""Real-time speed computation from sliding window."""

from __future__ import annotations

import time
from collections import deque

from ..protocol import SPEED_WINDOW


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
