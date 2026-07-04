"""mDNS service discovery (used by Client)."""

from __future__ import annotations

from zeroconf import ServiceBrowser, ServiceListener, Zeroconf

from .protocol import MOPS_SERVICE_TYPE
from .scheduler import NodeInfo, Scheduler


class NodeDiscovery(ServiceListener):
    """Discover MOPS servers via mDNS and manage the node pool."""

    def __init__(self, scheduler: Scheduler) -> None:
        self._scheduler = scheduler
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

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            self._add_node(info)

    def _add_node(self, info) -> None:
        ip = self._extract_ip(info)
        port = info.port
        weight = 1
        if info.properties:
            weight_bytes = info.properties.get(b"weight")
            if weight_bytes:
                try:
                    weight = int(weight_bytes)
                except (ValueError, TypeError):
                    weight = 1

        node = NodeInfo(
            ip=ip,
            port=port,
            weight=weight,
            name=info.name,
        )
        self._scheduler.add_node(node)

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
