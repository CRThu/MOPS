"""System service management (install/uninstall/start/stop)."""

from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

from loguru import logger

from .protocol import DEFAULT_BASE_PORT, STRATEGY_RANDOM


# Config file stores runtime params (mode, port, strategy)
_CONFIG_DIR = Path.home() / ".config" / "mops"
_CONFIG_FILE = _CONFIG_DIR / "config.json"


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


def _save_config(
    mode: str = "both",
    port: int = DEFAULT_BASE_PORT,
    strategy: str = STRATEGY_RANDOM,
    bind: str = "",
) -> None:
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    _CONFIG_FILE.write_text(json.dumps({"mode": mode, "port": port, "strategy": strategy, "bind": bind}))


def _load_config() -> dict:
    if _CONFIG_FILE.exists():
        return json.loads(_CONFIG_FILE.read_text())
    return {"mode": "both", "port": DEFAULT_BASE_PORT, "strategy": STRATEGY_RANDOM, "bind": ""}


# ── Public API ──


def install() -> None:
    """Install MOPS as a system service (no runtime params)."""
    if sys.platform == "win32":
        _install_windows()
    else:
        _install_linux()
    logger.info("Service installed")


def uninstall() -> None:
    """Uninstall MOPS system service."""
    if sys.platform == "win32":
        _uninstall_windows()
    else:
        _uninstall_linux()
    logger.info("Service uninstalled")


def start(
    mode: str = "both",
    port: int = DEFAULT_BASE_PORT,
    strategy: str = STRATEGY_RANDOM,
    bind: str = "",
) -> None:
    """Start the MOPS service with runtime params."""
    _save_config(mode=mode, port=port, strategy=strategy, bind=bind)
    logger.info(f"Config saved (mode={mode}, port={port}, strategy={strategy}, bind={bind!r})")
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


def _install_windows() -> None:
    exe = _get_exe_path()
    bin_path = f"{exe} --service"
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
    ExecStart={exe} --service
    Restart=on-failure
    RestartSec=5

    [Install]
    WantedBy=multi-user.target
""")


def _install_linux() -> None:
    exe = _get_exe_path()
    content = UNIT_CONTENT.format(exe=exe)
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
