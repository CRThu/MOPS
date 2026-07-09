"""MOPS CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys

from loguru import logger

from .protocol import (
    DEFAULT_API_PORT_OFFSET,
    DEFAULT_BASE_PORT,
    DEFAULT_CLIENT_PORT_OFFSET,
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


def _run_components(
    mode: str,
    base_port: int,
    listen: str,
    strategy: str,
    weight: int,
    bind: str,
) -> None:
    from .api import MopsApi
    from .stats import ConnectionTracker, TrafficHistory, TrafficStats

    client_port = base_port + DEFAULT_CLIENT_PORT_OFFSET
    api_port = base_port + DEFAULT_API_PORT_OFFSET

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
                port=base_port, weight=weight, bind=bind,
                stats=server_stats, conn_tracker=conn_tracker,
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
                # Unix: use add_signal_handler
                loop = asyncio.get_running_loop()
                loop.add_signal_handler(sig, _signal_handler)
            except (NotImplementedError, AttributeError):
                # Windows: use signal.signal (runs in main thread)
                signal.signal(sig, lambda s, f: _signal_handler())

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

        # Wait for shutdown signal
        await shutdown_event.wait()
        await _shutdown()

        # Cancel running tasks
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    asyncio.run(_run())


def cmd_run(args: argparse.Namespace) -> None:
    _setup_logger(args.service)
    base_port = args.port or DEFAULT_BASE_PORT
    mode = args.mode
    bind = getattr(args, "bind", "") or ""

    _run_components(mode, base_port, args.listen, args.strategy, args.weight, bind)


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
        port=args.port or DEFAULT_BASE_PORT,
        strategy=args.strategy,
        bind=getattr(args, "bind", "") or "",
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
    _setup_logger(args.service)
    from .dashboard import MopsDashboard
    d = MopsDashboard(port=args.port)
    asyncio.run(d.run())


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mops",
        description="MOPS - Multi-node Outbound Proxy System",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # run - direct execution (foreground)
    sp_run = subparsers.add_parser("run", help="Start MOPS directly (foreground)")
    sp_run.add_argument("mode", nargs="?", default="both",
                        choices=["server", "client", "both"],
                        help="Run mode (default: both)")
    sp_run.add_argument("--port", type=int, default=DEFAULT_BASE_PORT,
                        help="Base port (default: 10080)")
    sp_run.add_argument("--strategy", choices=[STRATEGY_RANDOM, STRATEGY_HASH],
                        default=STRATEGY_RANDOM, help="Load balance strategy")
    sp_run.add_argument("--listen", default="127.0.0.1",
                        help="Client listen address (default: 127.0.0.1)")
    sp_run.add_argument("--service", action="store_true",
                        help=argparse.SUPPRESS)
    sp_run.add_argument("--weight", type=int, default=1,
                        help="Server weight (default: 1)")
    sp_run.add_argument("--bind", default="",
                        help="IP address to advertise via mDNS (auto-detect if omitted)")
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

    # service start (runtime params)
    sp_svc_start = service_sub.add_parser("start", help="Start service")
    sp_svc_start.add_argument("--mode", choices=["server", "client", "both"],
                              default="both", help="Service mode (default: both)")
    sp_svc_start.add_argument("--port", type=int, default=DEFAULT_BASE_PORT,
                              help="Base port (default: 10080)")
    sp_svc_start.add_argument("--strategy", choices=[STRATEGY_RANDOM, STRATEGY_HASH],
                              default=STRATEGY_RANDOM, help="Load balance strategy")
    sp_svc_start.add_argument("--bind", default="",
                              help="IP address to advertise via mDNS (auto-detect if omitted)")
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
    sp_proxy_on.add_argument("--port", type=int, default=10081,
                             help="Proxy port (default: 10081)")
    sp_proxy_on.set_defaults(func=cmd_proxy_on)
    sp_proxy_off = proxy_sub.add_parser("off", help="Disable system proxy")
    sp_proxy_off.set_defaults(func=cmd_proxy_off)
    sp_proxy_stat = proxy_sub.add_parser("status", help="Show proxy status")
    sp_proxy_stat.set_defaults(func=cmd_proxy_status)

    # dashboard - standalone dashboard
    sp_dashboard = subparsers.add_parser("dashboard", help="Standalone dashboard (mDNS discovery)")
    sp_dashboard.add_argument("--port", type=int, default=10082,
                              help="Dashboard port (default: 10082)")
    sp_dashboard.add_argument("--service", action="store_true",
                              help=argparse.SUPPRESS)
    sp_dashboard.set_defaults(func=cmd_dashboard)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    if not args.command:
        # Default to "run both"
        args = parser.parse_args(["run", "both"])
        args.func(args)
        return

    # When --service flag is set, read config from file
    if getattr(args, "service", False):
        from .service import _load_config
        cfg = _load_config()
        args.mode = cfg.get("mode", "both")
        args.port = cfg.get("port", DEFAULT_BASE_PORT)
        args.strategy = cfg.get("strategy", STRATEGY_RANDOM)
        args.bind = cfg.get("bind", "")

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
