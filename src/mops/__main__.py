"""MOPS CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys
from pathlib import Path

from loguru import logger

from .protocol import (
    DEFAULT_API_PORT,
    DEFAULT_CLIENT_PORT,
    DEFAULT_DASHBOARD_PORT,
    DEFAULT_SERVER_PORT,
    STRATEGY_HASH,
    STRATEGY_RANDOM,
)
from .proxy import proxy_off, proxy_on, proxy_status


def _setup_logger(service_mode: bool = False) -> None:
    from .service import LOG_DIR

    logger.remove()
    log_file = LOG_DIR / "mops.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    logger.add(sys.stderr, level="DEBUG" if not service_mode else "INFO",
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

        # Suppress _ProactorBasePipeTransport._call_connection_lost errors on Windows.
        # When a connection is reset by the remote host, asyncio's ProactorEventLoop
        # tries to call socket.shutdown(SHUT_RDWR) in a callback, which fails with
        # ConnectionResetError. This is a known Python/Windows issue.
        def _loop_exception_handler(loop: asyncio.AbstractEventLoop, context: dict) -> None:
            exc = context.get("exception")
            if exc is not None:
                # ConnectionResetError from socket.shutdown() during cleanup
                if isinstance(exc, ConnectionResetError):
                    return
                # OSError with winerror=10054 (connection reset by peer)
                if isinstance(exc, OSError) and getattr(exc, "winerror", None) == 10054:
                    return
            loop.default_exception_handler(context)

        loop = asyncio.get_running_loop()
        loop.set_exception_handler(_loop_exception_handler)

        async def _update_traffic_history():
            """Periodically record aggregate traffic snapshot for speed computation."""
            while True:
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

        async def _shutdown():
            logger.info("Shutting down...")
            if server:
                await server.stop()
            if client:
                await client.stop()
            await api.stop()

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
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(_run())


def cmd_run(args: argparse.Namespace) -> None:
    _setup_logger()
    _run_components(
        mode=args.mode,
        server_port=args.server_port,
        client_port=args.client_port,
        api_port=args.api_port,
        listen=args.listen,
        advertise=args.advertise,
        strategy=args.strategy,
        weight=args.weight,
    )


def cmd_install(args: argparse.Namespace) -> None:
    _setup_logger()
    from .service import install
    install()


def cmd_uninstall(args: argparse.Namespace) -> None:
    _setup_logger()
    from .service import uninstall
    uninstall()


def cmd_start(args: argparse.Namespace) -> None:
    _setup_logger()
    from .service import start
    start(
        mode=args.mode,
        server_port=args.server_port,
        client_port=args.client_port,
        api_port=args.api_port,
        listen=args.listen,
        advertise=args.advertise,
        strategy=args.strategy,
        weight=args.weight,
    )


def cmd_stop(args: argparse.Namespace) -> None:
    _setup_logger()
    from .service import stop
    stop()


def cmd_status(args: argparse.Namespace) -> None:
    _setup_logger()
    from .service import status as svc_status
    print(json.dumps(svc_status(), indent=2))


def cmd_service_log(args: argparse.Namespace) -> None:
    from .service import LOG_DIR

    log_file = LOG_DIR / "mops.log"
    if not log_file.exists():
        print(f"No log file yet: {log_file}")
        return

    lines = log_file.read_text(encoding="utf-8").splitlines()
    if args.lines:
        lines = lines[-args.lines:]
    if args.search:
        term = args.search.lower()
        lines = [l for l in lines if term in l.lower()]

    for line in lines:
        print(line)


def cmd_proxy_on(args: argparse.Namespace) -> None:
    _setup_logger()
    proxy_on(args.port)


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

    # run - direct execution (foreground)
    sp_run = subparsers.add_parser("run", help="Start MOPS directly (foreground)")
    _add_common_args(sp_run)
    sp_run.set_defaults(func=cmd_run)

    # service - system service management
    sp_service = subparsers.add_parser("service", help="System service management")
    service_sub = sp_service.add_subparsers(dest="service_action", help="Service commands")

    # service install (no runtime params)
    sp_svc_install = service_sub.add_parser("install", help="Install system service")
    sp_svc_install.set_defaults(func=cmd_install)

    # service uninstall
    sp_svc_uninstall = service_sub.add_parser("uninstall", help="Uninstall system service")
    sp_svc_uninstall.set_defaults(func=cmd_uninstall)

    # service start (same params as run)
    sp_svc_start = service_sub.add_parser("start", help="Start service")
    _add_common_args(sp_svc_start)
    sp_svc_start.set_defaults(func=cmd_start)

    # service stop
    sp_svc_stop = service_sub.add_parser("stop", help="Stop service")
    sp_svc_stop.set_defaults(func=cmd_stop)

    # service status
    sp_svc_status = service_sub.add_parser("status", help="Query service status")
    sp_svc_status.set_defaults(func=cmd_status)

    # service log
    sp_svc_log = service_sub.add_parser("log", help="View service logs")
    sp_svc_log.add_argument("-n", "--lines", type=int, default=50,
                            help="Number of lines to show (default: 50)")
    sp_svc_log.add_argument("-s", "--search", type=str, default="",
                            help="Filter lines containing text")
    sp_svc_log.set_defaults(func=cmd_service_log)

    # proxy - system proxy control
    sp_proxy = subparsers.add_parser("proxy", help="System proxy control")
    proxy_sub = sp_proxy.add_subparsers(dest="proxy_action", help="Proxy commands")
    sp_proxy_on = proxy_sub.add_parser("on", help="Enable system proxy")
    sp_proxy_on.add_argument("--port", type=int, default=DEFAULT_CLIENT_PORT,
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

    # Handle nested subcommands validation
    if args.command == "service" and not getattr(args, "service_action", None):
        parser.parse_args([args.command, "--help"])
        sys.exit(1)

    if args.command == "proxy" and not getattr(args, "proxy_action", None):
        parser.parse_args([args.command, "--help"])
        sys.exit(1)

    args.func(args)


if __name__ == "__main__":
    main()
