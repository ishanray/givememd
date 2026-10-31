#!/usr/bin/env node
/** HTTP front door for local use: GET /amazon.com/dp/... -> text/markdown.   givememd-server [--port 8787]
 * See SECURITY.md before exposing it publicly. */
import { createServer } from 'node:http';
import { read, UnsafeURL } from './index.js';

const USAGE = '# givememd\n\nPut givememd in front of any URL to get LLM-ready markdown:\n\n    GET /amazon.com/dp/B0D1XD1ZV3\n    GET /https://react.dev/reference/react/useState?links=0\n';
const portArg = process.argv.indexOf('--port');
const port = portArg > -1 ? Number(process.argv[portArg + 1]) : 8787;

createServer(async (req, res) => {
  const send = (code: number, body: string, headers: Record<string, string> = {}) => {
    res.writeHead(code, { 'Content-Type': 'text/markdown; charset=utf-8', ...headers }); res.end(body);
  };
  let raw = (req.url ?? '/').slice(1);
  if (!raw || raw === 'favicon.ico') return send(200, USAGE);
  let links = true;
  if (/[?&]links=0$/.test(raw)) { raw = raw.replace(/[?&]links=0$/, ''); links = false; }
  try {
    const { markdown, result } = await read(raw, { links });
    if (markdown === null) return send(502, `# Could not read ${result.url}\n\nEvery tier was blocked from this server:\n${result.trace.map((t) => `- ${t}`).join('\n')}\n`);
    send(200, markdown, { 'X-Givememd-Tier': result.tier, 'X-Givememd-Source': result.url, 'X-Givememd-Partial': result.partial ? '1' : '0' });
  } catch (e) {
    send(e instanceof UnsafeURL ? 400 : 500, e instanceof UnsafeURL ? `# Refused\n\n${e.message}\n` : `# Error\n\n${(e as Error).message}\n`);
  }
}).listen(port, '127.0.0.1', () => console.log(`givememd on http://127.0.0.1:${port}/`));
