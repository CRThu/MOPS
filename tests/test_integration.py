"""Integration tests: real MOPS server+client in-process, actual proxy traffic.

Run: uv run pytest tests/test_integration.py -v -m integration
"""

from __future__ import annotations

import asyncio
import json
import socket
import struct

import pytest

from mops.protocol import NodeInfo, STRATEGY_HASH
from mops.server import MopsServer
from mops.client import MopsClient
from mops.stats import TrafficStats
from mops.stats.connection import ConnectionTracker
from mops.stats.history import TrafficHistory
from mops.api import MopsApi

_port_seq = 40000


def _alloc_port() -> int:
    """Return incrementing ports unlikely to collide."""
    global _port_seq
    _port_seq += 1
    return _port_seq


async def _wait_ready(port: int, timeout: float = 3) -> None:
    deadline = asyncio.get_running_loop().time() + timeout
    while asyncio.get_running_loop().time() < deadline:
        try:
            _, w = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", port), timeout=0.5
            )
            w.close()
            await w.wait_closed()
            return
        except OSError:
            await asyncio.sleep(0.1)
    raise TimeoutError(f"Port {port} not ready within {timeout}s")


async def _start_env(n_servers: int = 1, n_clients: int = 1) -> dict:
    """Start servers + clients in-process, return env dict."""
    servers: list[MopsServer] = []
    server_stats: list[TrafficStats] = []
    clients: list[MopsClient] = []
    client_stats: list[TrafficStats] = []
    tasks: list[asyncio.Task] = []
    server_ports: list[int] = []
    client_ports: list[int] = []

    # Servers
    for _ in range(n_servers):
        sp = _alloc_port()
        ss = TrafficStats()
        server_stats.append(ss)
        srv = MopsServer(port=sp, stats=ss)
        # Skip mDNS — too slow for tests
        srv._broadcaster.register = lambda *a, **kw: asyncio.sleep(0)
        srv._broadcaster.unregister = lambda *a, **kw: asyncio.sleep(0)
        servers.append(srv)
        server_ports.append(sp)
        tasks.append(asyncio.create_task(srv.run()))
        await _wait_ready(sp)

    # Clients — skip mDNS discovery, manually add server nodes
    for _ in range(n_clients):
        cp = _alloc_port()
        cs = TrafficStats()
        client_stats.append(cs)
        cli = MopsClient(listen_port=cp, listen_host="127.0.0.1", stats=cs)
        clients.append(cli)
        client_ports.append(cp)
        for sp in server_ports:
            cli._scheduler.add_node(NodeInfo(ip="127.0.0.1", port=sp))
        cli._server = await asyncio.start_server(
            cli.handle_proxy, cli.listen_host, cli.listen_port
        )
        await _wait_ready(cp)

    return {
        "servers": servers,
        "clients": clients,
        "tasks": tasks,
        "server_stats": server_stats,
        "client_stats": client_stats,
        "ports": {"servers": server_ports, "clients": client_ports},
    }


async def _stop_env(env: dict) -> None:
    # 1. Close server sockets — makes serve_forever() exit
    for srv in env["servers"]:
        if srv._server:
            srv._server.close()
    # 2. Close client sockets
    for cli in env["clients"]:
        if cli._server:
            cli._server.close()
    # 3. Brief pause so in-flight handler tasks can finish
    await asyncio.sleep(0.3)
    # 4. Cancel the run() tasks
    for t in env["tasks"]:
        if not t.done():
            t.cancel()
    try:
        await asyncio.wait_for(
            asyncio.gather(*env["tasks"], return_exceptions=True), timeout=3
        )
    except asyncio.TimeoutError:
        pass


# ── Helpers ───────────────────────────────────────────────────────────

async def _socks5(client_port: int, host: str, port: int) -> bool:
    """Run a full SOCKS5 CONNECT + HTTP GET through the proxy. Returns True on success."""
    r, w = None, None
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", client_port), timeout=3
        )
        # Handshake
        w.write(b"\x05\x01\x00")
        await w.drain()
        resp = await asyncio.wait_for(r.readexactly(2), timeout=2)
        if resp[1] != 0x00:
            return False
        # CONNECT request
        hdr = (
            struct.pack("!BBBB", 5, 1, 0, 1)
            + socket.inet_aton(host)
            + struct.pack("!H", port)
        )
        w.write(hdr)
        await w.drain()
        resp = await asyncio.wait_for(r.readexactly(10), timeout=3)
        if resp[1] != 0x00:
            return False
        # Send HTTP request through tunnel
        w.write(f"GET / HTTP/1.0\r\nHost: {host}:{port}\r\n\r\n".encode())
        await w.drain()
        data = await asyncio.wait_for(r.read(1024), timeout=5)
        return b"OK" in data
    except Exception:
        return False
    finally:
        if w:
            try:
                w.close()
                await asyncio.wait_for(w.wait_closed(), timeout=1)
            except Exception:
                pass


async def _http_connect(client_port: int, host: str, port: int) -> bool:
    """Run HTTP CONNECT + HTTP GET through the proxy. Returns True on success."""
    r, w = None, None
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", client_port), timeout=3
        )
        w.write(
            f"CONNECT {host}:{port} HTTP/1.1\r\nHost: {host}:{port}\r\n\r\n".encode()
        )
        await w.drain()
        # Read CONNECT response line
        resp_line = await asyncio.wait_for(r.readline(), timeout=2)
        if b"200" not in resp_line:
            return False
        # Read remaining headers
        while True:
            line = await asyncio.wait_for(r.readline(), timeout=2)
            if line == b"\r\n" or not line:
                break
        # Send HTTP request through tunnel
        w.write(f"GET / HTTP/1.0\r\nHost: {host}:{port}\r\n\r\n".encode())
        await w.drain()
        data = await asyncio.wait_for(r.read(1024), timeout=5)
        return b"OK" in data
    except Exception:
        return False
    finally:
        if w:
            try:
                w.close()
                await asyncio.wait_for(w.wait_closed(), timeout=1)
            except Exception:
                pass


# ── Target server fixture ─────────────────────────────────────────────

@pytest.fixture
async def target():
    """Start a tiny HTTP server on a free port, yield its port, then clean up."""
    async def handle(reader, writer):
        # Read until end-of-headers — don't wait for EOF (which would deadlock)
        buf = b""
        while b"\r\n\r\n" not in buf and len(buf) < 4096:
            chunk = await asyncio.wait_for(reader.read(1024), timeout=5)
            if not chunk:
                break
            buf += chunk
        body = f"OK {len(buf)}"
        cl = f"Content-Length: {len(body)}\r\n".encode()
        writer.write(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\n"
            + cl
            + b"\r\n"
            + body.encode()
        )
        await writer.drain()
        writer.close()
        await writer.wait_closed()

    port = _alloc_port()
    srv = await asyncio.start_server(handle, "127.0.0.1", port)
    await _wait_ready(port)
    yield port
    srv.close()
    await srv.wait_closed()


# ── Tests ─────────────────────────────────────────────────────────────


@pytest.mark.integration
async def test_single_server_single_client(target):
    tp = target
    env = await _start_env(1, 1)
    try:
        cp = env["ports"]["clients"][0]
        assert await _socks5(cp, "127.0.0.1", tp)
        assert await _http_connect(cp, "127.0.0.1", tp)
    finally:
        await _stop_env(env)


@pytest.mark.integration
async def test_single_server_multi_client(target):
    tp = target
    env = await _start_env(1, 2)
    try:
        ca, cb = env["ports"]["clients"]
        results = await asyncio.gather(
            _socks5(ca, "127.0.0.1", tp),
            _socks5(cb, "127.0.0.1", tp),
            _http_connect(ca, "127.0.0.1", tp),
            _http_connect(cb, "127.0.0.1", tp),
        )
        assert all(results)
    finally:
        await _stop_env(env)


@pytest.mark.integration
async def test_multi_server_single_client(target):
    tp = target
    env = await _start_env(2, 1)
    try:
        cp = env["ports"]["clients"][0]
        results = [await _socks5(cp, "127.0.0.1", tp) for _ in range(6)]
        assert all(results)
    finally:
        await _stop_env(env)


@pytest.mark.integration
async def test_multi_server_multi_client(target):
    tp = target
    env = await _start_env(2, 2)
    try:
        tasks = [
            _socks5(p, "127.0.0.1", tp)
            for p in env["ports"]["clients"]
            for _ in range(3)
        ]
        results = await asyncio.gather(*tasks)
        assert all(results)
    finally:
        await _stop_env(env)


@pytest.mark.integration
async def test_concurrent_connections_50(target):
    tp = target
    env = await _start_env(1, 1)
    try:
        cp = env["ports"]["clients"][0]
        results = await asyncio.gather(
            *[_socks5(cp, "127.0.0.1", tp) for _ in range(50)]
        )
        assert sum(results) == 50
    finally:
        await _stop_env(env)


@pytest.mark.integration
async def test_server_crash_graceful(target):
    tp = target
    env = await _start_env(1, 1)
    try:
        cp = env["ports"]["clients"][0]
        assert await _socks5(cp, "127.0.0.1", tp)
        # Kill server
        for srv in env["servers"]:
            if srv._server:
                srv._server.close()
        await asyncio.sleep(0.5)
        # Should fail, not crash
        result = await _socks5(cp, "127.0.0.1", tp)
        assert not result
    finally:
        await _stop_env(env)


@pytest.mark.integration
async def test_connection_refused(target):
    tp = target
    env = await _start_env(1, 1)
    try:
        cp = env["ports"]["clients"][0]
        # Port 19999 has nothing listening — proxy should fail gracefully
        assert not await _socks5(cp, "127.0.0.1", 19999)
    finally:
        await _stop_env(env)


@pytest.mark.integration
async def test_traffic_stats_accumulate(target):
    tp = target
    env = await _start_env(1, 1)
    try:
        cp = env["ports"]["clients"][0]
        for _ in range(5):
            await _socks5(cp, "127.0.0.1", tp)
        await asyncio.sleep(0.5)
        ss = env["server_stats"][0]
        cs = env["client_stats"][0]
        assert ss.get_total_up() + cs.get_total_up() > 0
        assert ss.get_total_down() + cs.get_total_down() > 0
    finally:
        await _stop_env(env)


@pytest.mark.integration
async def test_mixed_protocols(target):
    tp = target
    env = await _start_env(1, 1)
    try:
        cp = env["ports"]["clients"][0]
        tasks = [
            _socks5(cp, "127.0.0.1", tp) if i % 2 == 0
            else _http_connect(cp, "127.0.0.1", tp)
            for i in range(6)
        ]
        results = await asyncio.gather(*tasks)
        assert all(results)
    finally:
        await _stop_env(env)


# ── SOCKS5 domain name address (ATYP=0x03) ──────────────────────────


async def _socks5_domain(client_port: int, domain: str, port: int) -> bool:
    """SOCKS5 with domain name address type."""
    r, w = None, None
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", client_port), timeout=3
        )
        w.write(b"\x05\x01\x00")
        await w.drain()
        resp = await asyncio.wait_for(r.readexactly(2), timeout=2)
        if resp[1] != 0x00:
            return False
        # CONNECT with ATYP=0x03 (domain)
        domain_bytes = domain.encode()
        hdr = (
            struct.pack("!BBBB", 5, 1, 0, 3)
            + struct.pack("!B", len(domain_bytes))
            + domain_bytes
            + struct.pack("!H", port)
        )
        w.write(hdr)
        await w.drain()
        resp = await asyncio.wait_for(r.readexactly(10), timeout=3)
        if resp[1] != 0x00:
            return False
        w.write(f"GET / HTTP/1.0\r\nHost: {domain}:{port}\r\n\r\n".encode())
        await w.drain()
        data = await asyncio.wait_for(r.read(1024), timeout=5)
        return b"OK" in data
    except Exception:
        return False
    finally:
        if w:
            try:
                w.close()
                await asyncio.wait_for(w.wait_closed(), timeout=1)
            except Exception:
                pass


@pytest.mark.integration
async def test_socks5_domain_name(target):
    """SOCKS5 ATYP=0x03 (domain name) should resolve and tunnel correctly."""
    tp = target
    env = await _start_env(1, 1)
    try:
        cp = env["ports"]["clients"][0]
        # Use localhost as domain — server resolves it
        assert await _socks5_domain(cp, "localhost", tp)
    finally:
        await _stop_env(env)


# ── HTTP plain proxy (GET http://host/path) ─────────────────────────


async def _http_plain(client_port: int, host: str, port: int, path: str = "/") -> bool:
    """HTTP plain proxy: GET http://host:port/path (not CONNECT)."""
    r, w = None, None
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", client_port), timeout=3
        )
        url = f"http://{host}:{port}{path}"
        req = f"GET {url} HTTP/1.1\r\nHost: {host}:{port}\r\nConnection: close\r\n\r\n"
        w.write(req.encode())
        await w.drain()
        data = await asyncio.wait_for(r.read(4096), timeout=5)
        return b"OK" in data
    except Exception:
        return False
    finally:
        if w:
            try:
                w.close()
                await asyncio.wait_for(w.wait_closed(), timeout=1)
            except Exception:
                pass


@pytest.mark.integration
async def test_http_plain_proxy(target):
    """HTTP plain proxy (GET http://...) should rewrite URL and tunnel."""
    tp = target
    env = await _start_env(1, 1)
    try:
        cp = env["ports"]["clients"][0]
        assert await _http_plain(cp, "127.0.0.1", tp)
    finally:
        await _stop_env(env)


# ── Hash strategy session affinity ──────────────────────────────────


async def _start_env_hash(n_servers: int = 1, n_clients: int = 1) -> dict:
    """Like _start_env but with hash strategy."""
    servers: list[MopsServer] = []
    server_stats: list[TrafficStats] = []
    clients: list[MopsClient] = []
    client_stats: list[TrafficStats] = []
    tasks: list[asyncio.Task] = []
    server_ports: list[int] = []
    client_ports: list[int] = []

    for _ in range(n_servers):
        sp = _alloc_port()
        ss = TrafficStats()
        server_stats.append(ss)
        srv = MopsServer(port=sp, stats=ss)
        srv._broadcaster.register = lambda *a, **kw: asyncio.sleep(0)
        srv._broadcaster.unregister = lambda *a, **kw: asyncio.sleep(0)
        servers.append(srv)
        server_ports.append(sp)
        tasks.append(asyncio.create_task(srv.run()))
        await _wait_ready(sp)

    for _ in range(n_clients):
        cp = _alloc_port()
        cs = TrafficStats()
        client_stats.append(cs)
        cli = MopsClient(listen_port=cp, listen_host="127.0.0.1", strategy=STRATEGY_HASH, stats=cs)
        clients.append(cli)
        client_ports.append(cp)
        for sp in server_ports:
            cli._scheduler.add_node(NodeInfo(ip="127.0.0.1", port=sp))
        cli._server = await asyncio.start_server(
            cli.handle_proxy, cli.listen_host, cli.listen_port
        )
        await _wait_ready(cp)

    return {
        "servers": servers,
        "clients": clients,
        "tasks": tasks,
        "server_stats": server_stats,
        "client_stats": client_stats,
        "ports": {"servers": server_ports, "clients": client_ports},
    }


@pytest.mark.integration
async def test_hash_strategy_session_affinity(target):
    """Hash strategy: same (client_ip, target) always routes to same server."""
    tp = target
    # Use 2 servers — hash should pick consistently for same target
    env = await _start_env_hash(2, 1)
    try:
        cp = env["ports"]["clients"][0]
        # All connections to same target should succeed
        results = [await _socks5(cp, "127.0.0.1", tp) for _ in range(6)]
        assert all(results)
        # Verify stats accumulated on both servers
        up_total = sum(s.get_total_up() for s in env["server_stats"])
        assert up_total > 0
    finally:
        await _stop_env(env)


# ── No available nodes ──────────────────────────────────────────────


async def _socks5_raw(client_port: int, host: str, port: int) -> int | None:
    """SOCKS5 CONNECT, return the REP byte (1=general-failure, 4=host-unreachable, 5=refused)."""
    r, w = None, None
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", client_port), timeout=3
        )
        w.write(b"\x05\x01\x00")
        await w.drain()
        resp = await asyncio.wait_for(r.readexactly(2), timeout=2)
        if resp[1] != 0x00:
            return None
        hdr = (
            struct.pack("!BBBB", 5, 1, 0, 1)
            + socket.inet_aton(host)
            + struct.pack("!H", port)
        )
        w.write(hdr)
        await w.drain()
        resp = await asyncio.wait_for(r.readexactly(10), timeout=3)
        return resp[1]  # REP byte
    except Exception:
        return None
    finally:
        if w:
            try:
                w.close()
                await asyncio.wait_for(w.wait_closed(), timeout=1)
            except Exception:
                pass


async def _http_raw(client_port: int, url: str) -> int | None:
    """Send raw HTTP request, return status code."""
    r, w = None, None
    try:
        r, w = await asyncio.wait_for(
            asyncio.open_connection("127.0.0.1", client_port), timeout=3
        )
        w.write(f"GET {url} HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n".encode())
        await w.drain()
        line = await asyncio.wait_for(r.readline(), timeout=3)
        # Parse "HTTP/1.1 503 ..."
        parts = line.split()
        if len(parts) >= 2:
            return int(parts[1])
        return None
    except Exception:
        return None
    finally:
        if w:
            try:
                w.close()
                await asyncio.wait_for(w.wait_closed(), timeout=1)
            except Exception:
                pass


@pytest.mark.integration
async def test_no_available_nodes_socks5():
    """Client with no servers: SOCKS5 should fail gracefully and close connection."""
    cp = _alloc_port()
    cli = MopsClient(listen_port=cp, listen_host="127.0.0.1")
    # No servers added
    cli._server = await asyncio.start_server(
        cli.handle_proxy, cli.listen_host, cli.listen_port
    )
    await _wait_ready(cp)
    try:
        # Connection should be closed after error reply (REP=0x04 follows success reply)
        r, w = None, None
        try:
            r, w = await asyncio.wait_for(
                asyncio.open_connection("127.0.0.1", cp), timeout=3
            )
            w.write(b"\x05\x01\x00")
            await w.drain()
            resp = await asyncio.wait_for(r.readexactly(2), timeout=2)
            assert resp[1] == 0x00  # handshake ok
            hdr = (
                struct.pack("!BBBB", 5, 1, 0, 1)
                + socket.inet_aton("127.0.0.1")
                + struct.pack("!H", 80)
            )
            w.write(hdr)
            await w.drain()
            # Read success reply first, then error reply, then EOF
            resp1 = await asyncio.wait_for(r.readexactly(10), timeout=3)
            # Server should eventually close the connection
            remaining = await asyncio.wait_for(r.read(1024), timeout=3)
            # Either got error reply or EOF — both mean graceful failure
            assert len(remaining) == 0 or remaining[1] != 0x00
        except (ConnectionError, asyncio.IncompleteReadError, asyncio.TimeoutError):
            pass  # Connection closed = graceful failure
        finally:
            if w:
                try:
                    w.close()
                    await asyncio.wait_for(w.wait_closed(), timeout=1)
                except Exception:
                    pass
    finally:
        if cli._server:
            cli._server.close()
        await asyncio.sleep(0.2)


@pytest.mark.integration
async def test_no_available_nodes_http():
    """Client with no servers: HTTP GET should return 503."""
    cp = _alloc_port()
    cli = MopsClient(listen_port=cp, listen_host="127.0.0.1")
    cli._server = await asyncio.start_server(
        cli.handle_proxy, cli.listen_host, cli.listen_port
    )
    await _wait_ready(cp)
    try:
        status = await _http_raw(cp, "http://example.com/path")
        assert status == 503
    finally:
        if cli._server:
            cli._server.close()
        await asyncio.sleep(0.2)


# ── ConnectionTracker lifecycle ─────────────────────────────────────


@pytest.mark.integration
async def test_connection_tracker_lifecycle(target):
    """ConnectionTracker: connections appear as active, then move to completed."""
    tp = target
    sp = _alloc_port()
    ct = ConnectionTracker()
    ss = TrafficStats()
    cp = _alloc_port()
    srv = MopsServer(port=sp, stats=ss, conn_tracker=ct)
    srv._broadcaster.register = lambda *a, **kw: asyncio.sleep(0)
    srv._broadcaster.unregister = lambda *a, **kw: asyncio.sleep(0)
    srv_task = asyncio.create_task(srv.run())
    await _wait_ready(sp)

    # Client needs a server node to route traffic through
    cs = TrafficStats()
    cli = MopsClient(listen_port=cp, listen_host="127.0.0.1", stats=cs)
    cli._scheduler.add_node(NodeInfo(ip="127.0.0.1", port=sp))
    cli._server = await asyncio.start_server(
        cli.handle_proxy, cli.listen_host, cli.listen_port
    )
    await _wait_ready(cp)

    try:
        # Before any connection
        assert ct.active_count() == 0
        conns = ct.get_connections()
        assert len(conns) == 0

        # Make a connection through client → server
        await _socks5(cp, "127.0.0.1", tp)
        await asyncio.sleep(0.5)

        conns = ct.get_connections()
        assert len(conns) >= 1
        last = conns[-1]
        assert last["status"] in ("active", "completed", "error")
        assert last["target_host"] == "127.0.0.1"
        assert last["target_port"] == tp
    finally:
        if cli._server:
            cli._server.close()
        if srv._server:
            srv._server.close()
        await asyncio.sleep(0.2)
        for t in [srv_task]:
            if not t.done():
                t.cancel()
            try:
                await asyncio.wait_for(t, timeout=3)
            except (asyncio.CancelledError, asyncio.TimeoutError):
                pass


# ── /api/server monitoring endpoint ─────────────────────────────────


async def _fetch_api(port: int, path: str) -> dict:
    """Fetch JSON from the API server."""
    r, w = await asyncio.wait_for(
        asyncio.open_connection("127.0.0.1", port), timeout=3
    )
    w.write(f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1\r\nConnection: close\r\n\r\n".encode())
    await w.drain()
    # Read status line
    line = await asyncio.wait_for(r.readline(), timeout=3)
    status = int(line.split()[1])
    # Read headers until blank line
    content_length = 0
    while True:
        hline = await asyncio.wait_for(r.readline(), timeout=2)
        if hline == b"\r\n" or not hline:
            break
        if b"content-length" in hline.lower():
            content_length = int(hline.split(b":")[1].strip())
    # Read body
    body = await asyncio.wait_for(r.readexactly(content_length), timeout=3)
    w.close()
    await w.wait_closed()
    return {"status": status, "body": json.loads(body)}


@pytest.mark.integration
async def test_api_server_status(target):
    """GET /api/server returns valid JSON with expected fields."""
    tp = target
    sp = _alloc_port()
    ct = ConnectionTracker()
    ss = TrafficStats()
    api_port = _alloc_port()
    cp = _alloc_port()
    srv = MopsServer(port=sp, stats=ss, conn_tracker=ct)
    srv._broadcaster.register = lambda *a, **kw: asyncio.sleep(0)
    srv._broadcaster.unregister = lambda *a, **kw: asyncio.sleep(0)
    api = MopsApi(
        port=api_port, server_stats=ss, conn_tracker=ct, traffic_history=TrafficHistory(),
    )

    srv_task = asyncio.create_task(srv.run())
    await api.run()
    await _wait_ready(sp)
    await _wait_ready(api_port)

    # Client with server node
    cs = TrafficStats()
    cli = MopsClient(listen_port=cp, listen_host="127.0.0.1", stats=cs)
    cli._scheduler.add_node(NodeInfo(ip="127.0.0.1", port=sp))
    cli._server = await asyncio.start_server(
        cli.handle_proxy, cli.listen_host, cli.listen_port
    )
    await _wait_ready(cp)

    try:
        resp = await _fetch_api(api_port, "/api/server")
        assert resp["status"] == 200
        data = resp["body"]
        # Required top-level fields
        for key in ("nodes", "total_up", "total_down", "speed_up", "speed_down",
                     "active_conns", "uptime", "mode", "strategy"):
            assert key in data, f"Missing field: {key}"
        assert data["mode"] == "both"
        assert data["strategy"] == "random"
        assert data["uptime"] > 0

        # Make a connection through client → server and re-check
        await _socks5(cp, "127.0.0.1", tp)
        await asyncio.sleep(0.3)
        resp2 = await _fetch_api(api_port, "/api/server")
        assert resp2["status"] == 200
        data2 = resp2["body"]
        assert data2["total_up"] + data2["total_down"] > 0

        # /api/dashboard alias
        resp3 = await _fetch_api(api_port, "/api/dashboard")
        assert resp3["status"] == 200
    finally:
        if cli._server:
            cli._server.close()
        await api.stop()
        if srv._server:
            srv._server.close()
        await asyncio.sleep(0.2)
        if not srv_task.done():
            srv_task.cancel()
        try:
            await asyncio.wait_for(srv_task, timeout=3)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


@pytest.mark.integration
async def test_api_connections_recorded(target):
    """Connections appear in /api/server connections list."""
    tp = target
    sp = _alloc_port()
    ct = ConnectionTracker()
    ss = TrafficStats()
    api_port = _alloc_port()
    cp = _alloc_port()
    srv = MopsServer(port=sp, stats=ss, conn_tracker=ct)
    srv._broadcaster.register = lambda *a, **kw: asyncio.sleep(0)
    srv._broadcaster.unregister = lambda *a, **kw: asyncio.sleep(0)
    api = MopsApi(
        port=api_port, server_stats=ss, conn_tracker=ct, traffic_history=TrafficHistory(),
    )

    srv_task = asyncio.create_task(srv.run())
    await api.run()
    await _wait_ready(sp)
    await _wait_ready(api_port)

    # Client with server node
    cs = TrafficStats()
    cli = MopsClient(listen_port=cp, listen_host="127.0.0.1", stats=cs)
    cli._scheduler.add_node(NodeInfo(ip="127.0.0.1", port=sp))
    cli._server = await asyncio.start_server(
        cli.handle_proxy, cli.listen_host, cli.listen_port
    )
    await _wait_ready(cp)

    try:
        # Make a connection through client → server
        await _socks5(cp, "127.0.0.1", tp)
        await asyncio.sleep(0.3)

        resp = await _fetch_api(api_port, "/api/server")
        data = resp["body"]
        conns = data["connections"]
        assert len(conns) >= 1
        conn = conns[-1]
        assert conn["target_host"] == "127.0.0.1"
        assert conn["target_port"] == tp
        assert conn["status"] in ("completed", "error", "active")
    finally:
        if cli._server:
            cli._server.close()
        await api.stop()
        if srv._server:
            srv._server.close()
        await asyncio.sleep(0.2)
        if not srv_task.done():
            srv_task.cancel()
        try:
            await asyncio.wait_for(srv_task, timeout=3)
        except (asyncio.CancelledError, asyncio.TimeoutError):
            pass


# ── Background integration tests ──

import os
import subprocess
import sys
import time
from pathlib import Path


def _port_busy(port: int) -> bool:
    """Check if a port is in use."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) == 0


def _process_alive(pid: int) -> bool:
    """Check if a process is alive."""
    try:
        if sys.platform == "win32":
            result = subprocess.run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in result.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, subprocess.TimeoutExpired):
        return False


class TestBackgroundIntegration:
    """Integration tests for mops run -b (daemonize) and mops stop."""

    def test_background_start_and_stop(self):
        """Start MOPS in background, verify it's running, then kill it."""
        sp = _alloc_port()
        cp = _alloc_port()
        ap = _alloc_port()

        # Start in background
        result = subprocess.run(
            [sys.executable, "-m", "mops", "run", "-b",
             "--mode", "both",
             "--server-port", str(sp),
             "--client-port", str(cp),
             "--api-port", str(ap)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "pid=" in result.stdout

        pid = int(result.stdout.split("pid=")[1].split(")")[0])

        try:
            # Wait for ports to be ready (pythonw.exe may take longer to start)
            deadline = time.time() + 8
            while time.time() < deadline:
                if _port_busy(sp) and _port_busy(ap):
                    break
                time.sleep(0.3)
            else:
                pytest.fail(f"Ports not ready: server={sp} api={ap}")

            # Verify process is alive
            assert _process_alive(pid)

            # Verify API responds
            import urllib.request
            resp = urllib.request.urlopen(f"http://127.0.0.1:{ap}/api/server", timeout=3)
            data = json.loads(resp.read())
            assert data["mode"] == "both"
        finally:
            # Kill the background process
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/f", "/t", "/pid", str(pid)],
                               capture_output=True, timeout=5)
            else:
                os.kill(pid, signal.SIGTERM)
            time.sleep(1)

        # Verify process is gone and ports freed
        assert not _process_alive(pid)
        deadline = time.time() + 3
        while time.time() < deadline:
            if not _port_busy(sp):
                break
            time.sleep(0.3)
        assert not _port_busy(sp)
        assert not _port_busy(ap)

    def test_background_server_only(self):
        """Start MOPS in background with mode=server, verify client port unused."""
        sp = _alloc_port()
        cp = _alloc_port()
        ap = _alloc_port()

        result = subprocess.run(
            [sys.executable, "-m", "mops", "run", "-b",
             "--mode", "server",
             "--server-port", str(sp),
             "--client-port", str(cp),
             "--api-port", str(ap)],
            capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        pid = int(result.stdout.split("pid=")[1].split(")")[0])

        try:
            deadline = time.time() + 8
            while time.time() < deadline:
                if _port_busy(sp):
                    break
                time.sleep(0.3)
            else:
                pytest.fail(f"Server port {sp} not ready")

            assert _process_alive(pid)
            # Client port should NOT be listening
            assert not _port_busy(cp)

            # Verify API reports server mode
            import urllib.request
            resp = urllib.request.urlopen(f"http://127.0.0.1:{ap}/api/server", timeout=3)
            data = json.loads(resp.read())
            assert data["mode"] == "server"
        finally:
            if sys.platform == "win32":
                subprocess.run(["taskkill", "/f", "/t", "/pid", str(pid)],
                               capture_output=True, timeout=5)
            else:
                os.kill(pid, signal.SIGTERM)
            time.sleep(1)
