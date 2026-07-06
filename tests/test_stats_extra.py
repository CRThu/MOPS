"""Tests for NodeRegistry and TrafficHistory."""

import time
from unittest.mock import patch

import pytest

from mops.stats import NodeRecord, NodeRegistry, TrafficHistory


class TestNodeRegistry:
    def test_record_seen(self):
        reg = NodeRegistry()
        reg.record_seen("192.168.1.1", 10080, 10082, "server-a")
        nodes = reg.get_all()
        assert len(nodes) == 1
        rec = nodes["192.168.1.1:10080"]
        assert rec.ip == "192.168.1.1"
        assert rec.port == 10080
        assert rec.api_port == 10082
        assert rec.hostname == "server-a"
        assert rec.first_seen > 0
        assert rec.last_seen > 0

    def test_record_seen_updates(self):
        reg = NodeRegistry()
        reg.record_seen("192.168.1.1", 10080, 10082, "server-a")
        old_first = reg.get_all()["192.168.1.1:10080"].first_seen
        time.sleep(0.01)
        reg.record_seen("192.168.1.1", 10080, 10083, "server-a-v2")
        rec = reg.get_all()["192.168.1.1:10080"]
        assert rec.api_port == 10083
        assert rec.hostname == "server-a-v2"
        assert rec.first_seen == old_first  # first_seen preserved
        assert rec.last_seen >= old_first

    def test_mark_offline(self):
        reg = NodeRegistry()
        reg.record_seen("192.168.1.1", 10080, 10082, "server-a")
        reg.mark_offline("192.168.1.1", 10080)
        rec = reg.get_all()["192.168.1.1:10080"]
        assert rec.last_seen == 0

    def test_mark_offline_nonexistent(self):
        reg = NodeRegistry()
        # Should not crash
        reg.mark_offline("192.168.1.99", 10080)

    def test_prune_removes_old_offline(self):
        reg = NodeRegistry(ttl=0)  # ttl=0 => prune immediately
        reg.record_seen("192.168.1.1", 10080, 10082, "server-a")
        reg.mark_offline("192.168.1.1", 10080)
        reg.prune()
        assert len(reg.get_all()) == 0

    def test_prune_keeps_online(self):
        reg = NodeRegistry(ttl=0)
        reg.record_seen("192.168.1.1", 10080, 10082, "server-a")
        reg.prune()
        assert len(reg.get_all()) == 1

    def test_prune_keeps_recent_offline(self):
        reg = NodeRegistry(ttl=3600)
        reg.record_seen("192.168.1.1", 10080, 10082, "server-a")
        reg.mark_offline("192.168.1.1", 10080)
        reg.prune()
        assert len(reg.get_all()) == 1  # too recent to prune


class TestTrafficHistory:
    def test_empty(self):
        h = TrafficHistory()
        assert h.compute_speed() == (0, 0)

    def test_single_sample(self):
        h = TrafficHistory()
        h.record(1000, 2000, 5)
        assert h.compute_speed() == (0, 0)

    def test_compute_speed(self):
        h = TrafficHistory(capacity=5)
        h.record(0, 0, 1)
        time.sleep(0.05)
        h.record(500, 1000, 2)
        up, down = h.compute_speed()
        assert up > 0
        assert down > 0
        # Speed should be roughly 500/0.05 = 10000 bytes/s
        assert 1000 < up < 100000
        assert 2000 < down < 200000

    def test_capacity_limit(self):
        h = TrafficHistory(capacity=3)
        for i in range(10):
            h.record(i * 100, i * 200, i)
        assert len(h._samples) == 3
        # Last two samples
        assert h._samples[-1]["up"] == 900
        assert h._samples[-2]["up"] == 800

    def test_speed_with_same_timestamp(self):
        h = TrafficHistory()
        h.record(100, 200, 1)
        h.record(100, 200, 1)  # same values
        assert h.compute_speed() == (0, 0)
