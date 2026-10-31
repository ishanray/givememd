"""HTTP front door: GET /amazon.com/dp/... -> text/markdown.

    python -m givememd.server --port 8787
"""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import tiktoken

from . import UnsafeURL, read

USAGE = """# givememd

Put givememd in front of any URL to get LLM-ready markdown:

    GET /amazon.com/dp/B0D1XD1ZV3
    GET /https://react.dev/reference/react/useState?links=0
"""
enc = tiktoken.get_encoding('o200k_base')


class Handler(BaseHTTPRequestHandler):
    def send(self, code, body, headers=()):
        data = body.encode()
        self.send_response(code)
        self.send_header('Content-Type', 'text/markdown; charset=utf-8')
        self.send_header('Content-Length', str(len(data)))
        for k, v in headers:
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        raw = self.path[1:]
        if not raw or raw == 'favicon.ico':
            return self.send(200, USAGE)
        # our own options ride on a trailing ?links=0; everything else belongs to the target URL
        target, links = raw, True
        if urlsplit(raw).query.endswith('links=0'):
            target, links = raw[:-len('links=0')].rstrip('?&'), False
        try:
            md, r = read(target, links=links)
        except UnsafeURL as e:
            return self.send(400, f'# Refused\n\n{e}\n')
        if md is None:
            trace = '\n'.join(f'- {t}' for t in r.trace)
            return self.send(502, f'# Could not read {r.url}\n\nEvery tier was blocked from this server:\n{trace}\n\n'
                                  'Run givememd locally (`python -m givememd <url>` or the MCP server) '
                                  'to fetch from your own IP.\n', [('X-Givememd-Trace', ' | '.join(r.trace))])
        self.send(200, md, [('X-Givememd-Tier', r.tier), ('X-Givememd-Tokens', str(len(enc.encode(md)))),
                            ('X-Givememd-Source', r.url), ('X-Givememd-Partial', '1' if r.partial else '0')])

    def log_message(self, fmt, *args):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', type=int, default=8787)
    a = ap.parse_args()
    print(f'givememd on http://127.0.0.1:{a.port}/')
    ThreadingHTTPServer(('127.0.0.1', a.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
