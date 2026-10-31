"""Local MCP server: every fetch runs on the caller's machine, from the caller's IP.

    claude mcp add givememd -- uvx --from 'givememd[mcp]' givememd-mcp
"""
from mcp.server.mcpserver import MCPServer

from . import UnsafeURL, read

mcp = MCPServer('givememd')


@mcp.tool()
def read_url(url: str, links: bool = True) -> str:
    """Read any web page as clean, LLM-ready markdown: page text, structured data hidden in
    the page (listings, products) as tables, and cleaned links. Fetches from this machine."""
    try:
        md, r = read(url, links=links)
    except UnsafeURL as e:
        return f'Refused: {e}'
    if md is None:
        return f'Could not read {r.url}. Tiers tried:\n' + '\n'.join(r.trace)
    return md


def main():
    mcp.run()


if __name__ == '__main__':
    main()
