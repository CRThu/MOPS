"""Shared web utilities for aiohttp apps (static files, index routing)."""

from __future__ import annotations

from pathlib import Path

from aiohttp import web

_STATIC_DIR = Path(__file__).parent / "static"


def setup_static_routes(app: web.Application) -> None:
    """Add static file routes and root-level asset routes to an aiohttp app."""
    if _STATIC_DIR.is_dir():
        app.router.add_static("/static", _STATIC_DIR)
        for f in _STATIC_DIR.iterdir():
            if f.suffix in (".js", ".css"):
                app.router.add_get(f"/{f.name}", lambda req, fp=f: web.FileResponse(fp))


async def serve_index(request: web.Request) -> web.Response:
    """Serve the built index.html, or a fallback message."""
    index = _STATIC_DIR / "index.html"
    if index.exists():
        return web.FileResponse(index)
    return web.Response(
        text="<h1>MOPS Dashboard</h1><p>No frontend built yet. Run: cd web && bun run build</p>",
        content_type="text/html",
    )
