"""MOPS CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import sys
import threading
from pathlib import Path

from loguru import logger

from .protocol import (
    DEFAULT_API_PORT,
    DEFAULT_CLIENT_HOST,
    DEFAULT_CLIENT_PORT,
    DEFAULT_DASHBOARD_PORT,
    DEFAULT_SERVER_PORT,
    STRATEGY_HASH,
    STRATEGY_RANDOM,
)
from .proxy import proxy_off, proxy_on, proxy_status

LOG_DIR = Path.home() / ".mops" / "logs"


def _is_alive(pid: int) -> bool:
    """Check if a process is alive."""
    try:
        if sys.platform == "win32":
            import subprocess
            r = subprocess.run(
                ["tasklist", "/fi", f"PID eq {pid}", "/fo", "csv", "/nh"],
                capture_output=True, text=True, timeout=5,
            )
            return str(pid) in r.stdout
        else:
            os.kill(pid, 0)
            return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def _setup_logger() -> None:
    logger.remove()
    log_file = LOG_DIR / "mops.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    logger.add(sys.stderr, level="DEBUG",
               format="{time:HH:mm:ss} | {level} | {message}")
    logger.add(str(log_file), level="DEBUG", rotation="10 MB",
               retention="7 days", format=fmt)


def _load_config_file(path: str) -> dict:
    """Load config from a JSON file. Returns empty dict if file doesn't exist."""
    p = Path(path)
    if not p.exists():
        logger.error(f"Config file not found: {path}")
        sys.exit(1)
    return json.loads(p.read_text(encoding="utf-8"))


def _apply_config(args: argparse.Namespace, cfg: dict) -> None:
    """Apply config file values to args (only if not already set by CLI)."""
    for key in ("mode", "listen", "advertise", "strategy"):
        if key in cfg and getattr(args, key, None) is None:
            setattr(args, key, cfg[key])
    for key in ("server_port", "client_port", "api_port", "weight"):
        if key in cfg and getattr(args, key, None) is None:
            setattr(args, key, cfg[key])


def _run_components(
    mode: str,
    server_port: int,
    client_port: int,
    api_port: int,
    listen: str,
    advertise: str,
    strategy: str,
    weight: int,
) -> None:
    from .api import MopsApi
    from .stats import ConnectionTracker, TrafficHistory, TrafficStats

    # Create stats objects based on mode
    server_stats = TrafficStats() if mode in ("server", "both") else None
    client_stats = TrafficStats() if mode in ("client", "both") else None
    conn_tracker = ConnectionTracker() if mode in ("server", "both") else None
    traffic_history = TrafficHistory() if mode in ("server", "both") else None

    async def _run():
        from .client import MopsClient
        from .server import MopsServer

        server = None
        client = None

        if mode in ("server", "both"):
            server = MopsServer(
                port=server_port, api_port=api_port, weight=weight,
                bind=advertise, stats=server_stats, conn_tracker=conn_tracker,
            )
        if mode in ("client", "both"):
            client = MopsClient(
                listen_port=client_port, listen_host=listen,
                strategy=strategy, stats=client_stats,
            )

        api = MopsApi(
            port=api_port,
            server_stats=server_stats,
            client_stats=client_stats,
            conn_tracker=conn_tracker,
            traffic_history=traffic_history,
            mode=mode,
            strategy=strategy,
            client_listen=listen,
            client_port=client_port,
        )

        shutdown_event = asyncio.Event()

        def _signal_handler():
            shutdown_event.set()

        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop = asyncio.get_running_loop()
                loop.add_signal_handler(sig, _signal_handler)
            except (NotImplementedError, AttributeError):
                signal.signal(sig, lambda s, f: _signal_handler())

        # Suppress noisy errors from asyncio callbacks on Windows.
        # The ProactorEventLoop raises various WinErrors in _call_connection_lost
        # and other callbacks when connections are reset or networks go down.
        # These are expected during normal proxy operation and should not crash
        # or spam the log.
        _SUPPRESSED_WINERRORS = {64, 121, 10053, 10054, 10056, 10057, 1225, 1235}

        def _loop_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
            exc = context.get("exception")
            if exc is not None:
                # Suppress all Windows-specific connection/network errors
                winerror = getattr(exc, "winerror", None)
                if winerror is not None and winerror in _SUPPRESSED_WINERRORS:
                    return
                # Suppress ConnectionResetError / ConnectionAbortedError on any platform
                if isinstance(exc, (ConnectionResetError, ConnectionAbortedError)):
                    return
                # Suppress "cannot write to closing transport" RuntimeError
                if isinstance(exc, RuntimeError) and "closing" in str(exc).lower():
                    return
            loop.default_exception_handler(context)

        loop = asyncio.get_running_loop()
        loop.set_exception_handler(_loop_exception_handler)

        async def _update_traffic_history():
            """Periodically record aggregate traffic snapshot for speed computation."""
            while True:
                try:
                    await asyncio.sleep(1)
                    if not traffic_history:
                        continue
                    total_up = 0
                    total_down = 0
                    active_conns = 0
                    if server_stats:
                        total_up += server_stats.get_total_up()
                        total_down += server_stats.get_total_down()
                        active_conns += server_stats.active_conns
                    if client_stats:
                        total_up += client_stats.get_total_up()
                        total_down += client_stats.get_total_down()
                        active_conns += client_stats.active_conns
                    traffic_history.record(total_up, total_down, active_conns)
                except asyncio.CancelledError:
                    return
                except Exception as e:
                    logger.debug(f"Traffic history error: {type(e).__name__}: {e}")

        async def _shutdown():
            logger.info("Shutting down...")
            if server:
                await server.stop()
            if client:
                await client.stop()
            try:
                await api.stop()
            except Exception as e:
                logger.debug(f"API stop warning: {e}")

        await api.run()

        tasks = []
        if server:
            tasks.append(asyncio.create_task(server.run()))
        if client:
            tasks.append(asyncio.create_task(client.run()))
        if traffic_history:
            tasks.append(asyncio.create_task(_update_traffic_history()))

        await shutdown_event.wait()
        await _shutdown()

        for t in tasks:
            t.cancel()
        try:
            await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=5)
        except asyncio.TimeoutError:
            logger.debug("Task cleanup timed out, proceeding with shutdown")

    asyncio.run(_run())


def cmd_run(args: argparse.Namespace) -> None:
    if args.background:
        _daemonize(args)
        return
    _setup_logger()
    _run_components(
        mode=args.mode, server_port=args.server_port,
        client_port=args.client_port, api_port=args.api_port,
        listen=args.listen, advertise=args.advertise,
        strategy=args.strategy, weight=args.weight,
    )


def _daemonize(args: argparse.Namespace) -> None:
    """Launch self in background and exit."""
    import subprocess

    config_path = getattr(args, "config", None)

    # Detect current runner: uv → use `uv run python`; otherwise use sys.executable
    if Path(sys.prefix) / "pyvenv.cfg" != Path(sys.prefix) / "pyvenv.cfg":
        pass  # venv
    uv = shutil.which("uv")
    if uv:
        cmd = [uv, "run", "python", "-m", "mops", "run"]
    else:
        cmd = [sys.executable, "-m", "mops", "run"]

    cmd += [
        "--mode", args.mode,
        "--server-port", str(args.server_port),
        "--client-port", str(args.client_port),
        "--api-port", str(args.api_port),
        "--listen", args.listen,
        "--advertise", args.advertise or "",
        "--strategy", args.strategy,
        "--weight", str(args.weight),
    ]
    if config_path:
        cmd += ["-c", config_path]

    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_DIR / "mops.log"
    project_dir = str(Path(__file__).resolve().parent.parent.parent)

    if sys.platform == "win32":
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        p = subprocess.Popen(
            cmd, cwd=project_dir, startupinfo=si,
            creationflags=subprocess.CREATE_NO_WINDOW,
            stdout=open(log, "a"), stderr=subprocess.STDOUT,
        )
    else:
        if os.fork() > 0:
            os._exit(0)
        os.setsid()
        p = subprocess.Popen(
            cmd, cwd=project_dir,
            stdout=open(log, "a"), stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
        )

    (LOG_DIR / "mops.pid").write_text(str(p.pid))
    print(f"MOPS started in background (pid={p.pid})")


def cmd_stop(args: argparse.Namespace) -> None:
    """Stop the background MOPS process."""
    pid_file = LOG_DIR / "mops.pid"
    if not pid_file.exists():
        print("No PID file found. MOPS may not be running in background.")
        return

    pid = int(pid_file.read_text().strip())
    if not _is_alive(pid):
        print(f"Process {pid} not found (already stopped?)")
        pid_file.unlink(missing_ok=True)
        return

    try:
        if sys.platform == "win32":
            import subprocess
            subprocess.run(["taskkill", "/f", "/t", "/pid", str(pid)],
                           capture_output=True, check=True)
        else:
            os.kill(pid, signal.SIGTERM)
        print(f"MOPS stopped (pid={pid})")
    except (ProcessLookupError, OSError):
        print(f"Process {pid} not found (already stopped?)")
    finally:
        pid_file.unlink(missing_ok=True)


def cmd_proxy_on(args: argparse.Namespace) -> None:
    _setup_logger()
    host = DEFAULT_CLIENT_HOST
    port = DEFAULT_CLIENT_PORT
    if args.target:
        if ":" in args.target:
            host, port_str = args.target.rsplit(":", 1)
            port = int(port_str)
        else:
            host = args.target
    if args.host:
        host = args.host
    if args.port:
        port = args.port
    proxy_on(host, port)


def cmd_proxy_off(args: argparse.Namespace) -> None:
    _setup_logger()
    proxy_off()


def cmd_proxy_status(args: argparse.Namespace) -> None:
    _setup_logger()
    print(json.dumps(proxy_status(), indent=2))


def cmd_dashboard(args: argparse.Namespace) -> None:
    _setup_logger()
    from .dashboard import MopsDashboard
    d = MopsDashboard(port=args.port)
    asyncio.run(d.run())


def _add_common_args(p: argparse.ArgumentParser) -> None:
    """Add shared arguments to a subparser."""
    p.add_argument("--mode", choices=["server", "client", "both"],
                   default=None, help="Run mode (default: both)")
    p.add_argument("--server-port", type=int, default=None,
                   help=f"Server TCP port (default: {DEFAULT_SERVER_PORT})")
    p.add_argument("--client-port", type=int, default=None,
                   help=f"Client proxy port (default: {DEFAULT_CLIENT_PORT})")
    p.add_argument("--api-port", type=int, default=None,
                   help=f"REST API port (default: {DEFAULT_API_PORT})")
    p.add_argument("--listen", default=None,
                   help="Client listen address (default: 127.0.0.1)")
    p.add_argument("--advertise", default=None,
                   help="mDNS advertise address (auto-detect if omitted)")
    p.add_argument("--strategy", choices=[STRATEGY_RANDOM, STRATEGY_HASH],
                   default=None, help="Load balance strategy (default: random)")
    p.add_argument("--weight", type=int, default=None,
                   help="Server weight (default: 1)")
    p.add_argument("-c", "--config", default=None,
                   help="Load config from JSON file")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mops",
        description="MOPS - Multi-node Outbound Proxy System",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run - direct execution (foreground) or background
    sp_run = subparsers.add_parser("run", help="Start MOPS")
    sp_run.add_argument("-b", "--background", action="store_true",
                        help="Run in background and exit")
    _add_common_args(sp_run)
    sp_run.set_defaults(func=cmd_run)

    # stop - stop background process
    sp_stop = subparsers.add_parser("stop", help="Stop background MOPS process")
    sp_stop.set_defaults(func=cmd_stop)

    # proxy - system proxy control
    sp_proxy = subparsers.add_parser("proxy", help="System proxy control")
    proxy_sub = sp_proxy.add_subparsers(dest="proxy_action", help="Proxy commands")
    sp_proxy_on = proxy_sub.add_parser("on", help="Enable system proxy")
    sp_proxy_on.add_argument("target", nargs="?", default=None,
                             help="host:port (e.g. 192.168.1.100:10081)")
    sp_proxy_on.add_argument("--host", default=None,
                             help="Proxy host (default: 127.0.0.1)")
    sp_proxy_on.add_argument("--port", type=int, default=None,
                             help=f"Proxy port (default: {DEFAULT_CLIENT_PORT})")
    sp_proxy_on.set_defaults(func=cmd_proxy_on)
    sp_proxy_off = proxy_sub.add_parser("off", help="Disable system proxy")
    sp_proxy_off.set_defaults(func=cmd_proxy_off)
    sp_proxy_stat = proxy_sub.add_parser("status", help="Show proxy status")
    sp_proxy_stat.set_defaults(func=cmd_proxy_status)

    # dashboard - standalone dashboard
    sp_dashboard = subparsers.add_parser("dashboard", help="Standalone dashboard (mDNS discovery)")
    sp_dashboard.add_argument("--port", type=int, default=DEFAULT_DASHBOARD_PORT,
                              help=f"Dashboard port (default: {DEFAULT_DASHBOARD_PORT})")
    sp_dashboard.set_defaults(func=cmd_dashboard)

    return parser


def _apply_defaults(args: argparse.Namespace) -> None:
    """Fill in default values for any None config-overridable args."""
    defaults = {
        "mode": "both",
        "server_port": DEFAULT_SERVER_PORT,
        "client_port": DEFAULT_CLIENT_PORT,
        "api_port": DEFAULT_API_PORT,
        "listen": "127.0.0.1",
        "advertise": "",
        "strategy": STRATEGY_RANDOM,
        "weight": 1,
    }
    for key, val in defaults.items():
        if getattr(args, key, None) is None:
            setattr(args, key, val)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        # Default to "run" with defaults
        args = parser.parse_args(["run"])
        _apply_defaults(args)
        args.func(args)
        return

    # Load config file if -c/--config is specified
    config_path = getattr(args, "config", None)
    if config_path:
        cfg = _load_config_file(config_path)
        _apply_config(args, cfg)

    # Fill in defaults for any remaining None values
    _apply_defaults(args)

    if args.command == "proxy" and not getattr(args, "proxy_action", None):
        parser.parse_args([args.command, "--help"])
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
