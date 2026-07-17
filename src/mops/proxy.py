"""System proxy configuration (Windows registry / Linux env vars)."""

from __future__ import annotations

import ctypes
import os
import platform
import subprocess

if platform.system() == "Windows":
    import winreg

from loguru import logger


def _get_proxy_url(host: str, port: int) -> str:
    return f"{host}:{port}"


def proxy_on(host: str = "127.0.0.1", port: int = 10081) -> None:
    """Enable system-wide proxy."""
    if platform.system() == "Windows":
        _windows_proxy_on(host, port)
    elif platform.system() == "Darwin":
        _macos_proxy_on(host, port)
    else:
        _linux_proxy_on(host, port)
    logger.info(f"Proxy enabled: {_get_proxy_url(host, port)}")


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
_ENV_KEY = r"Environment"


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


def _windows_proxy_on(host: str, port: int) -> None:
    proxy = _get_proxy_url(host, port)
    _win_reg_set("ProxyEnable", 1)
    _win_reg_set("ProxyServer", proxy)
    _win_reg_set("ProxyOverride", "localhost;127.*;<local>")
    _set_env_vars(f"http://{proxy}", f"http://{proxy}")
    _notify_windows()


def _windows_proxy_off() -> None:
    _win_reg_set("ProxyEnable", 0)
    _clear_env_vars()
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


def _set_env_vars(http_proxy: str, https_proxy: str) -> None:
    """Persist http_proxy/https_proxy env vars via registry (survives new terminals)."""
    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENV_KEY, 0, winreg.KEY_SET_VALUE)
    winreg.SetValueEx(key, "http_proxy", 0, winreg.REG_SZ, http_proxy)
    winreg.SetValueEx(key, "https_proxy", 0, winreg.REG_SZ, https_proxy)
    winreg.SetValueEx(key, "HTTP_PROXY", 0, winreg.REG_SZ, http_proxy)
    winreg.SetValueEx(key, "HTTPS_PROXY", 0, winreg.REG_SZ, https_proxy)
    winreg.SetValueEx(key, "no_proxy", 0, winreg.REG_SZ, "localhost,127.0.0.1")
    winreg.SetValueEx(key, "NO_PROXY", 0, winreg.REG_SZ, "localhost,127.0.0.1")
    winreg.CloseKey(key)
    # Also set for current process
    os.environ["http_proxy"] = http_proxy
    os.environ["https_proxy"] = https_proxy
    os.environ["HTTP_PROXY"] = http_proxy
    os.environ["HTTPS_PROXY"] = https_proxy
    os.environ["no_proxy"] = "localhost,127.0.0.1"
    os.environ["NO_PROXY"] = "localhost,127.0.0.1"
    logger.info("Environment variables set (restart terminal to take effect)")


def _clear_env_vars() -> None:
    """Remove http_proxy/https_proxy env vars from registry and current process."""
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "no_proxy", "NO_PROXY"):
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, _ENV_KEY, 0, winreg.KEY_SET_VALUE)
            winreg.DeleteValue(key, var)
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass
        os.environ.pop(var, None)
    logger.info("Environment variables cleared (restart terminal to take effect)")


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


def _linux_proxy_on(host: str, port: int) -> None:
    proxy = f"http://{_get_proxy_url(host, port)}"
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

def _macos_proxy_on(host: str, port: int) -> None:
    services = _get_active_network_services()
    for svc in services:
        subprocess.run(["networksetup", "-setwebproxy", svc, host, str(port)], capture_output=True)
        subprocess.run(["networksetup", "-setsecurewebproxy", svc, host, str(port)], capture_output=True)
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
