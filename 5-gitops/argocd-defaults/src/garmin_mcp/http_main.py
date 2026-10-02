"""HTTP entrypoint — streamable-HTTP transport (K8s/remote deployment).

Spawns an HTTP server that serves the MCP protocol over HTTP.  This is
the correct transport for container/Kubernetes deployments: Claude Desktop
uses the ``garmin-mcp`` (stdio) entry point locally, while remote
clients communicate over HTTP.

Both entry points import the same ``mcp`` object from ``server.py``,
so tool definitions never drift between the two deployment modes.

Environment variables:
    MCP_HOST:  Bind address (default ``0.0.0.0``).
    MCP_PORT:  Bind port   (default ``8000``).
"""

import os

from garmin_mcp.server import mcp


def main():
    host = os.environ.get("MCP_HOST", "0.0.0.0")
    port = int(os.environ.get("MCP_PORT", "8000"))
    mcp.run(transport="http", host=host, port=port)


if __name__ == "__main__":
    main()
