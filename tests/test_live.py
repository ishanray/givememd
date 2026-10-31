"""End-to-end against the real internet. Run with: pytest -m live"""
import json, socket, subprocess, sys, threading, time, urllib.request
from http.server import ThreadingHTTPServer

import pytest

from givememd.server import Handler

pytestmark = pytest.mark.live
PAGE = 'react.dev/reference/react/useState'


@pytest.fixture(scope='module')
def server():
    s = socket.socket(); s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]; s.close()
    httpd = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f'http://127.0.0.1:{port}'
    httpd.shutdown()


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            return r.status, dict(r.headers), r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read().decode()


def test_server_reads_a_page(server):
    code, h, body = get(f'{server}/{PAGE}')
    assert code == 200, body[:300]
    assert h['X-Givememd-Tier'] == 'http'
    assert 'useState(initialState)' in body and '```js\nconst [state, setState] = useState(initialState)\n```' in body
    assert '{/*' not in body and '<Intro>' not in body     # react.dev serves MDX; we clean it


def test_server_links_off(server):
    page = 'en.wikipedia.org/wiki/Markdown'
    _, _, on = get(f'{server}/{page}')
    _, _, off = get(f'{server}/{page}?links=0')
    assert '## Links' in on and '## Links' not in off and len(off) < len(on)


def test_server_refuses_ssrf(server):
    code, _, body = get(f'{server}/http://169.254.169.254/latest/meta-data/')
    assert code == 400 and 'non-public' in body


def test_mcp_server_over_stdio():
    """Spawn the MCP server the way Claude Code would and call read_url."""
    import asyncio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def run():
        params = StdioServerParameters(command=sys.executable, args=['-m', 'givememd.mcp_server'])
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                tools = [t.name for t in (await s.list_tools()).tools]
                out = await s.call_tool('read_url', {'url': PAGE, 'links': False})
                return tools, out.content[0].text

    tools, text = asyncio.run(run())
    assert tools == ['read_url']
    assert 'useState(initialState)' in text


def test_cli():
    p = subprocess.run([sys.executable, '-m', 'givememd', PAGE, '--no-links', '--trace'], capture_output=True, text=True, timeout=120)
    assert p.returncode == 0 and 'http: ok' in p.stderr and 'useState' in p.stdout
