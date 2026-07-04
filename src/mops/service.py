"""System service management (install/uninstall/start/stop)."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
from pathlib import Path

from loguru import logger


def _get_exe_path() -> str:
    """Get the path to the current executable or python -m mops."""
    if getattr(sys, "frozen", False):
        return sys.executable
    return f"{sys.executable} -m mops"


def _run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    logger.debug(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        stderr = result.stderr.strip()
        logger.error(f"Command failed (rc={result.returncode}): {stderr}")
        raise RuntimeError(f"Command failed: {stderr}")
    return result


def install(mode: str, base_port: int, strategy: str = "random") -> None:
    """Install MOPS as a system service."""
    if sys.platform == "win32":
        _install_windows(mode, base_port, strategy)
    else:
        _install_linux(mode, base_port, strategy)
    logger.info(f"Service installed (mode={mode}, port={base_port}, strategy={strategy})")


def uninstall() -> None:
    """Uninstall MOPS system service."""
    if sys.platform == "win32":
        _uninstall_windows()
    else:
        _uninstall_linux()
    logger.info("Service uninstalled")


def start() -> None:
    """Start the MOPS service."""
    if sys.platform == "win32":
        _run_cmd(["sc", "start", "MOPS"])
    else:
        _run_cmd(["systemctl", "start", "mops"])
    logger.info("Service started")


def stop() -> None:
    """Stop the MOPS service."""
    if sys.platform == "win32":
        _run_cmd(["sc", "stop", "MOPS"])
    else:
        _run_cmd(["systemctl", "stop", "mops"])
    logger.info("Service stopped")


def status() -> dict:
    """Query service status."""
    if sys.platform == "win32":
        return _status_windows()
    else:
        return _status_linux()


# ── Windows ──

def _install_windows(mode: str, base_port: int, strategy: str) -> None:
    exe = _get_exe_path()
    bin_path = f"{exe} --service --mode {mode} --port {base_port} --strategy {strategy}"
    _run_cmd([
        "sc", "create", "MOPS",
        f"binPath= {bin_path}",
        "start= auto",
        "DisplayName= MOPS Service",
    ])


def _uninstall_windows() -> None:
    _run_cmd(["sc", "stop", "MOPS"], check=False)
    _run_cmd(["sc", "delete", "MOPS"])


def _status_windows() -> dict:
    result = _run_cmd(["sc", "query", "MOPS"], check=False)
    running = "RUNNING" in result.stdout
    return {"running": running, "raw": result.stdout.strip()}


# ── Linux (systemd) ──

_SERVICE_DIR = Path("/etc/systemd/system")

UNIT_CONTENT = textwrap.dedent("""\
    [Unit]
    Description=MOPS - Multi-node Outbound Proxy System
    After=network.target

    [Service]
    Type=simple
    ExecStart={exe} --service --mode {mode} --port {port} --strategy {strategy}
    Restart=on-failure
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
""")


def _install_linux(mode: str, base_port: int, strategy: str) -> None:
    exe = _get_exe_path()
    content = UNIT_CONTENT.format(
        exe=exe, mode=mode, port=base_port, strategy=strategy
    )
    unit_path = _SERVICE_DIR / "mops.service"
    unit_path.write_text(content)
    _run_cmd(["systemctl", "daemon-reload"])
    _run_cmd(["systemctl", "enable", "mops"])


def _uninstall_linux() -> None:
    _run_cmd(["systemctl", "stop", "mops"], check=False)
    _run_cmd(["systemctl", "disable", "mops"], check=False)
    unit_path = _SERVICE_DIR / "mops.service"
    if unit_path.exists():
        unit_path.unlink()
    _run_cmd(["systemctl", "daemon-reload"])


def _status_linux() -> dict:
    result = _run_cmd(["systemctl", "is-active", "mops"], check=False)
    running = result.stdout.strip() == "active"
    return {"running": running, "raw": result.stdout.strip()}
