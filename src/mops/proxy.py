"""System proxy configuration (Windows registry / Linux env vars)."""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess

if platform.system() == "Windows":
    import winreg

from loguru import logger


def _get_proxy_url(port: int) -> str:
    return f"127.0.0.1:{port}"


def proxy_on(port: int) -> None:
    """Enable system-wide proxy."""
    if platform.system() == "Windows":
        _windows_proxy_on(port)
    elif platform.system() == "Darwin":
        _macos_proxy_on(port)
    else:
        _linux_proxy_on(port)
    logger.info(f"Proxy enabled: {_get_proxy_url(port)}")


def proxy_off() -> None:
    """Disable system-wide proxy."""
    if platform.system() == "Windows":
        _windows_proxy_off()
    elif platform.system() == "Darwin":
        _macos_proxy_off()
    else:
        _linux_proxy_off()
    logger.info("Proxy disabled")


def proxy_status() -> dict:
    """Return current proxy status as dict."""
    if platform.system() == "Windows":
        return _windows_proxy_status()
    elif platform.system() == "Darwin":
        return _macos_proxy_status()
    else:
        return _linux_proxy_status()


# --- Windows ---

_WINDOWS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"


def _win_reg_set(name: str, value) -> None:
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WINDOWS_KEY, 0, winreg.KEY_SET_VALUE)
    reg_type = winreg.REG_DWORD if isinstance(value, int) else winreg.REG_SZ
    winreg.SetValueEx(key, name, 0, reg_type, value)
    winreg.CloseKey(key)


def _win_reg_get(name: str):
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _WINDOWS_KEY, 0, winreg.KEY_READ)
        value, _ = winreg.QueryValueEx(key, name)
        winreg.CloseKey(key)
        return value
    except FileNotFoundError:
        return None


def _windows_proxy_on(port: int) -> None:
    proxy = _get_proxy_url(port)
    _win_reg_set("ProxyEnable", 1)
    _win_reg_set("ProxyServer", proxy)
    _win_reg_set("ProxyOverride", "localhost;127.*;<local>")
    _notify_windows()


def _windows_proxy_off() -> None:
    _win_reg_set("ProxyEnable", 0)
    _notify_windows()


def _windows_proxy_status() -> dict:
    enabled = _win_reg_get("ProxyEnable")
    server = _win_reg_get("ProxyServer")
    return {
        "platform": "windows",
        "enabled": bool(enabled),
        "server": server or "",
    }


def _notify_windows() -> None:
    """Notify Windows IE/system about proxy change."""
    try:
        wininet = ctypes.windll.wininet
        wininet.InternetSetOptionW(0, 39, 0, 0)  # INTERNET_OPTION_SETTINGS_CHANGED
        wininet.InternetSetOptionW(0, 37, 0, 0)  # INTERNET_OPTION_REFRESH
    except Exception:
        pass


# --- Linux ---

_PROXY_ENV_FILE = os.path.expanduser("~/.mops_proxy_env")

_ENV_BLOCK = """# MOPS proxy settings - source this file to enable proxy
export http_proxy="{proxy}"
export https_proxy="{proxy}"
export HTTP_PROXY="{proxy}"
export HTTPS_PROXY="{proxy}"
export no_proxy="localhost,127.0.0.1"
export NO_PROXY="localhost,127.0.0.1"
"""


def _linux_proxy_on(port: int) -> None:
    proxy = f"http://{_get_proxy_url(port)}"
    with open(_PROXY_ENV_FILE, "w") as f:
        f.write(_ENV_BLOCK.format(proxy=proxy))
    logger.info(f"Run: source {_PROXY_ENV_FILE}")


def _linux_proxy_off() -> None:
    if os.path.exists(_PROXY_ENV_FILE):
        os.remove(_PROXY_ENV_FILE)
    logger.info("Run: unset http_proxy https_proxy HTTP_PROXY HTTPS_PROXY")


def _linux_proxy_status() -> dict:
    return {
        "platform": "linux",
        "enabled": os.path.exists(_PROXY_ENV_FILE),
        "server": os.environ.get("http_proxy", ""),
    }


# --- macOS ---

def _macos_proxy_on(port: int) -> None:
    proxy = _get_proxy_url(port)
    services = _get_active_network_services()
    for svc in services:
        subprocess.run(["networksetup", "-setwebproxy", svc, "127.0.0.1", str(port)], capture_output=True)
        subprocess.run(["networksetup", "-setsecurewebproxy", svc, "127.0.0.1", str(port)], capture_output=True)
    if services:
        logger.info(f"Proxy set on: {', '.join(services)}")


def _macos_proxy_off() -> None:
    services = _get_active_network_services()
    for svc in services:
        subprocess.run(["networksetup", "-setwebproxystate", svc, "off"], capture_output=True)
        subprocess.run(["networksetup", "-setsecurewebproxystate", svc, "off"], capture_output=True)


def _macos_proxy_status() -> dict:
    services = _get_active_network_services()
    enabled = False
    server = ""
    if services:
        result = subprocess.run(
            ["networksetup", "-getwebproxy", services[0]],
            capture_output=True, text=True,
        )
        for line in result.stdout.splitlines():
            if "Enabled:" in line:
                enabled = "Yes" in line
            elif "Server:" in line:
                server = line.split(":", 1)[1].strip()
    return {"platform": "macos", "enabled": enabled, "server": server}


def _get_active_network_services() -> list[str]:
    try:
        result = subprocess.run(
            ["networksetup", "-listallnetworkservices"],
            capture_output=True, text=True,
        )
    except (FileNotFoundError, subprocess.SubprocessError, OSError) as e:
        logger.warning(f"Failed to list network services: {e}")
        return []
    services = []
    for line in result.stdout.splitlines()[1:]:
        if not line.startswith("*"):
            services.append(line.strip())
    return services
