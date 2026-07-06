"""mDNS service discovery (used by Client and Dashboard)."""

from __future__ import annotations

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from .protocol import MOPS_SERVICE_TYPE
from .scheduler import NodeInfo, Scheduler

# Type hint for NodeRegistry to avoid circular imports
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from .stats import NodeRegistry


class NodeDiscovery(ServiceListener):
    """Discover MOPS servers via mDNS and manage the node pool."""

    def __init__(self, scheduler: Scheduler, registry: "NodeRegistry | None" = None) -> None:
        self._scheduler = scheduler
        self._registry = registry
        self._zc: Zeroconf | None = None
        self._browser: ServiceBrowser | None = None

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if not info:
            return
        self._add_node(info)

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if not info:
            # Service expired, try to remove by name
            self._scheduler.remove_by_name(name)
            return
        ip = self._extract_ip(info)
        port = info.port
        self._scheduler.remove_node(f"{ip}:{port}")
        if self._registry:
            self._registry.mark_offline(ip, port)

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            self._add_node(info)

    def _add_node(self, info) -> None:
        ip = self._extract_ip(info)
        port = info.port
        weight = 1
        api_port = port + 2  # default: base_port + 2
        hostname = ""

        if info.properties:
            weight_bytes = info.properties.get(b"weight")
            if weight_bytes:
                try:
                    weight = int(weight_bytes)
                except (ValueError, TypeError):
                    weight = 1
            api_port_bytes = info.properties.get(b"api_port")
            if api_port_bytes:
                try:
                    api_port = int(api_port_bytes)
                except (ValueError, TypeError):
                    api_port = port + 2

        # Extract hostname from service name:
        # mops-server-{hostname}-{port}._mops-proxy._tcp.local.
        service_name = info.name or ""
        if service_name.startswith("mops-server-"):
            rest = service_name.split("mops-server-", 1)[1]
            # Remove mDNS suffix if present
            for suffix in ("._mops-proxy._tcp.local.", "._mops-proxy._tcp.local"):
                if rest.endswith(suffix):
                    rest = rest[:-len(suffix)]
                    break
            # rest = "{hostname}-{port}", strip trailing port
            parts = rest.rsplit("-", 1)
            if len(parts) == 2 and parts[1].isdigit():
                hostname = parts[0]
            else:
                hostname = rest
        if not hostname:
            hostname = ip

        node = NodeInfo(
            ip=ip,
            port=port,
            api_port=api_port,
            weight=weight,
            name=info.name,
            hostname=hostname,
        )
        self._scheduler.add_node(node)

        if self._registry:
            self._registry.record_seen(ip, port, api_port, hostname)

    def _extract_ip(self, info) -> str:
        addrs = info.parsed_addresses()
        if addrs:
            return addrs[0]
        return "unknown"

    def start(self) -> None:
        self._zc = Zeroconf()
        self._browser = ServiceBrowser(self._zc, MOPS_SERVICE_TYPE, self)

    def stop(self) -> None:
        if self._browser:
            self._browser.cancel()
        if self._zc:
            self._zc.close()
