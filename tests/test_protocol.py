"""Tests for protocol constants and scheduler logic."""

from mops.protocol import (
    BUFFER_SIZE,
    DEFAULT_BASE_PORT,
    MDNS_TTL,
    MAX_FAILS,
    MOPS_SERVICE_TYPE,
    RECOVERY_INTERVAL,
    STRATEGY_HASH,
    STRATEGY_RANDOM,
)


def test_constants_values():
    assert DEFAULT_BASE_PORT == 10080
    assert MDNS_TTL == 60
    assert MAX_FAILS == 2
    assert RECOVERY_INTERVAL == 30
    assert BUFFER_SIZE == 65536
    assert MOPS_SERVICE_TYPE == "_mops-proxy._tcp.local."
    assert STRATEGY_RANDOM == "random"
    assert STRATEGY_HASH == "hash"
