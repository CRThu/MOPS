"""Tests for protocol constants, header build/parse."""

import json

import pytest

from mops.protocol import (
    BUFFER_SIZE,
    DEFAULT_API_PORT,
    DEFAULT_CLIENT_PORT,
    DEFAULT_DASHBOARD_PORT,
    DEFAULT_SERVER_PORT,
    MDNS_TTL,
    MAX_FAILS,
    MOPS_SERVICE_TYPE,
    NODE_HISTORY_TTL,
    PROTOCOL_VERSION,
    RECOVERY_INTERVAL,
    SPEED_WINDOW,
    STRATEGY_HASH,
    STRATEGY_RANDOM,
    build_header,
    parse_header,
)


def test_constants_values():
    assert DEFAULT_SERVER_PORT == 10080
    assert DEFAULT_CLIENT_PORT == 10081
    assert DEFAULT_API_PORT == 10082
    assert DEFAULT_DASHBOARD_PORT == 10100
    assert MDNS_TTL == 60
    assert MAX_FAILS == 2
    assert RECOVERY_INTERVAL == 30
    assert BUFFER_SIZE == 65536
    assert MOPS_SERVICE_TYPE == "_mops-proxy._tcp.local."
    assert STRATEGY_RANDOM == "random"
    assert STRATEGY_HASH == "hash"
    assert NODE_HISTORY_TTL == 3600
    assert SPEED_WINDOW == 5


class TestBuildHeader:
    def test_basic(self):
        h = build_header("example.com", 443)
        data = json.loads(h)
        assert data["version"] == PROTOCOL_VERSION
        assert data["host"] == "example.com:443"
        assert "client_port" not in data
        assert "client_host" not in data

    def test_with_client_port(self):
        h = build_header("example.com", 80, client_port=10090)
        data = json.loads(h)
        assert data["client_port"] == 10090

    def test_with_client_host(self):
        h = build_header("example.com", 443, client_port=10090, client_host="Carrot-PC")
        data = json.loads(h)
        assert data["client_host"] == "Carrot-PC"
        assert data["client_port"] == 10090

    def test_ends_with_newline(self):
        h = build_header("example.com", 443)
        assert h.endswith(b"\n")

    def test_compact_json(self):
        h = build_header("a.com", 80)
        assert b": " not in h  # no spaces in separators


class TestParseHeader:
    def test_basic(self):
        raw = build_header("example.com", 443)
        host, port, cp, ch = parse_header(raw)
        assert host == "example.com"
        assert port == 443
        assert cp == 0
        assert ch == ""

    def test_with_all_fields(self):
        raw = build_header("google.com", 80, client_port=10090, client_host="MyPC")
        host, port, cp, ch = parse_header(raw)
        assert host == "google.com"
        assert port == 80
        assert cp == 10090
        assert ch == "MyPC"

    def test_empty_header_raises(self):
        with pytest.raises(ValueError, match="empty"):
            parse_header(b"\n")

    def test_non_json_raises(self):
        with pytest.raises(ValueError, match="invalid header format"):
            parse_header(b"example.com:80\n")

    def test_missing_host_raises(self):
        with pytest.raises(KeyError):
            parse_header(b'{"version":1}\n')

    def test_invalid_host_format_raises(self):
        with pytest.raises(ValueError):
            parse_header(b'{"version":1,"host":"noport"}\n')

    def test_roundtrip(self):
        h = build_header("example.com", 443, client_port=10090, client_host="TestHost")
        host, port, cp, ch = parse_header(h)
        assert (host, port, cp, ch) == ("example.com", 443, 10090, "TestHost")
