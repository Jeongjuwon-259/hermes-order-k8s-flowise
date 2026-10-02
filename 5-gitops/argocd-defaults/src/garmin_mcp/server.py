"""Garmin Running MCP server — transport-agnostic tool definitions.

This module owns the single `mcp` (FastMCP) instance and every tool/route
registered on it. It never decides *how* the server is run — that's
`stdio_main.py` (local, Claude Desktop) or `http_main.py` (remote/K8s).
Both entrypoints import this same `mcp` object, so tool definitions never
drift between the two deployment modes.
"""

from datetime import datetime, timezone

from mcp.server.fastmcp import FastMCP

from garmin_mcp.auth import _has_saved_tokens, create_client
from garmin_mcp.client import GarminClient

mcp = FastMCP("garmin-mcp")

_client: GarminClient | None = None


def get_client() -> GarminClient:
    """Get the authenticated Garmin client (lazy initialization)."""
    global _client
    if _client is None:
        garmin = create_client()
        _client = GarminClient(garmin)
    return _client


@mcp.custom_route("/health", methods=["GET"])
async def health_check(request):
    """Liveness/readiness probe for streamable-http deployments (K8s etc).

    Deliberately does NOT touch Garmin (no login, no API call) — this is a
    fast "is the process up and serving requests" check, not a check that
    Garmin auth is valid. It also does not require auth itself, so it's
    safe to leave open even behind an auth-gated deployment. Under stdio
    transport this route is simply never reached (no HTTP server exists).
    """
    from starlette.responses import JSONResponse

    return JSONResponse({
        "status": "ok",
        "server": "garmin-mcp",
        "time": datetime.now(timezone.utc).isoformat(),
        "garmin_tokens_present": _has_saved_tokens(),
    })


# Register all tools
from garmin_mcp.tools import register_tools  # noqa: E402

register_tools(mcp)
