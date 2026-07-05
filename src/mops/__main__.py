"""MOPS CLI entry point."""

from __future__ import annotations

import argparse
import asyncio
import json
import signal
import sys

from loguru import logger

from .protocol import (
    DEFAULT_BASE_PORT,
    LOG_DIR,
    STRATEGY_HASH,
    STRATEGY_RANDOM,
)
from .proxy import proxy_off, proxy_on, proxy_status
from .stats import ConnectionTracker, TrafficStats


def _setup_logger(service_mode: bool = False) -> None:
    logger.remove()
    log_file = LOG_DIR / "mops.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    fmt = "{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}"
    logger.add(sys.stderr, level="DEBUG" if not service_mode else "INFO",
               format="{time:HH:mm:ss} | {level} | {message}")
    logger.add(str(log_file), level="DEBUG", rotation="10 MB",
               retention="7 days", format=fmt)


def _run_server(base_port: int, weight: int, bind: str = "") -> None:
    from .api import MopsApi
    from .server import MopsServer

    api_port = base_port + 2
    stats = TrafficStats()
    conn_tracker = ConnectionTracker()

    async def _server():
        server = MopsServer(port=base_port, weight=weight, bind=bind, stats=stats, conn_tracker=conn_tracker)
        api = MopsApi(port=api_port, server_stats=stats, mode="server", conn_tracker=conn_tracker)

        async def shutdown():
            await server.stop()
            await api.stop()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.ensure_future(shutdown()))
            except NotImplementedError:
                pass

        await api.run()
        await server.run()

    asyncio.run(_server())


def _run_client(base_port: int, listen: str, strategy: str) -> None:
    from .api import MopsApi
    from .client import MopsClient

    client_port = base_port + 1
    api_port = base_port + 2
    stats = TrafficStats()

    async def _client():
        client = MopsClient(
            listen_port=client_port, listen_host=listen,
            strategy=strategy, stats=stats,
        )
        api = MopsApi(port=api_port, client_stats=stats, mode="client")

        async def shutdown():
            await client.stop()
            await api.stop()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.ensure_future(shutdown()))
            except NotImplementedError:
                pass

        await api.run()
        await client.run()

    asyncio.run(_client())


def _run_both(base_port: int, listen: str, strategy: str, weight: int, bind: str = "") -> None:
    from .api import MopsApi
    from .client import MopsClient
    from .server import MopsServer

    client_port = base_port + 1
    api_port = base_port + 2
    server_stats = TrafficStats()
    client_stats = TrafficStats()
    conn_tracker = ConnectionTracker()

    async def _both():
        server = MopsServer(port=base_port, weight=weight, bind=bind, stats=server_stats, conn_tracker=conn_tracker)
        client = MopsClient(
            listen_port=client_port, listen_host=listen,
            strategy=strategy, stats=client_stats,
        )
        api = MopsApi(
            port=api_port,
            server_stats=server_stats,
            client_stats=client_stats,
            mode="both",
            strategy=strategy,
            server_port=base_port,
            client_listen=listen,
            client_port=client_port,
            conn_tracker=conn_tracker,
        )

        async def shutdown():
            await server.stop()
            await client.stop()
            await api.stop()

        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, lambda: asyncio.ensure_future(shutdown()))
            except NotImplementedError:
                pass

        await api.run()
        await asyncio.gather(server.run(), client.run())

    asyncio.run(_both())


def cmd_run(args: argparse.Namespace) -> None:
    _setup_logger(args.service)
    base_port = args.port or DEFAULT_BASE_PORT
    mode = args.mode
    bind = getattr(args, "bind", "") or ""

    if mode == "server":
        _run_server(base_port, args.weight, bind)
    elif mode == "client":
        _run_client(base_port, args.listen, args.strategy)
    else:
        _run_both(base_port, args.listen, args.strategy, args.weight, bind)


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
