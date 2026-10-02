"""Local entrypoint — stdio transport.

Spawned as a subprocess by Claude Desktop (or any MCP client that launches
the server itself). This is the default, unauthenticated-by-design
transport: the client that spawns the process is the only thing that can
talk to it, so no separate auth layer is needed here.
"""

from garmin_mcp.server import mcp


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
