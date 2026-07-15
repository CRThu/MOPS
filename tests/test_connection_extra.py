"""Tests for ConnectionTracker error state tracking."""

import pytest

from mops.stats.connection import ConnectionTracker


class TestConnectionTrackerErrorTracking:
    """Test error state tracking in ConnectionTracker."""

    def test_end_with_error_reason_marks_error(self):
        tracker = ConnectionTracker()
        conn_id = tracker.start("127.0.0.1", "example.com", 443)
        tracker.end(conn_id, error_reason="timeout")

        conns = tracker.get_connections()
        assert len(conns) == 1
        assert conns[0]["status"] == "error"
        assert conns[0]["error_reason"] == "timeout"

    def test_end_without_error_marks_completed(self):
        tracker = ConnectionTracker()
        conn_id = tracker.start("127.0.0.1", "example.com", 443)
        tracker.end(conn_id)

        conns = tracker.get_connections()
        assert len(conns) == 1
        assert conns[0]["status"] == "completed"
        assert conns[0]["error_reason"] == ""

    def test_active_count_with_errors(self):
        tracker = ConnectionTracker()
        id1 = tracker.start("127.0.0.1", "a.com", 443)
        id2 = tracker.start("127.0.0.1", "b.com", 443)
        id3 = tracker.start("127.0.0.1", "c.com", 443)

        assert tracker.active_count() == 3

        tracker.end(id1, error_reason="timeout")
        assert tracker.active_count() == 2

        tracker.end(id2)
        assert tracker.active_count() == 1

    def test_connection_record_has_error_fields(self):
        tracker = ConnectionTracker()
        conn_id = tracker.start("127.0.0.1", "example.com", 443, client_port=10081, client_host="test-host")
        tracker.end(conn_id, error_reason="connect-timeout (example.com:443)")

        conns = tracker.get_connections()
        conn = conns[0]
        assert conn["client_ip"] == "127.0.0.1"
        assert conn["client_port"] == 10081
        assert conn["client_host"] == "test-host"
        assert conn["target_host"] == "example.com"
        assert conn["target_port"] == 443
        assert conn["status"] == "error"
        assert conn["error_reason"] == "connect-timeout (example.com:443)"
        assert conn["started_at"] > 0
        assert conn["ended_at"] > conn["started_at"]

    def test_prune_old_completed(self):
        tracker = ConnectionTracker(history_minutes=0)  # immediate prune
        conn_id = tracker.start("127.0.0.1", "example.com", 443)
        tracker.end(conn_id)

        conns = tracker.get_connections()
        assert len(conns) == 0

    def test_end_nonexistent_conn_id(self):
        tracker = ConnectionTracker()
        tracker.end("999", error_reason="timeout")  # should not raise

    def test_concurrent_access(self):
        import threading
        tracker = ConnectionTracker()

        def worker():
            for _ in range(100):
                conn_id = tracker.start("127.0.0.1", "example.com", 443)
                tracker.end(conn_id, error_reason="timeout")

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        conns = tracker.get_connections()
        assert len(conns) == 400
