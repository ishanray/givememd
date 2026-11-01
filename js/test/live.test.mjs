// End-to-end against the real web: npm run test:live
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { execFile, spawn } from 'node:child_process';
import { promisify } from 'node:util';
import { Client } from '@modelcontextprotocol/sdk/client/index.js';
import { StdioClientTransport } from '@modelcontextprotocol/sdk/client/stdio.js';

const run = promisify(execFile);
const dist = (f) => new URL(`../dist/${f}`, import.meta.url).pathname;
const PAGE = 'react.dev/reference/react/useState';

test('cli reads a page', async () => {
  const { stdout, stderr } = await run('node', [dist('cli.js'), PAGE, '--no-links', '--trace'], { timeout: 120_000 });
  assert.match(stderr, /http: ok/);
  assert.ok(stdout.includes('useState(initialState)'));
});

test('cli refuses private targets', async () => {
  await assert.rejects(run('node', [dist('cli.js'), 'http://169.254.169.254/latest/']), (e) => /refused/.test(e.stderr));
});

test('http server serves markdown', async () => {
  const port = 18000 + Math.floor(Math.random() * 1000);
  const srv = spawn('node', [dist('server.js'), '--port', String(port)]);
  await new Promise((r) => srv.stdout.once('data', r));
  try {
    const res = await fetch(`http://127.0.0.1:${port}/en.wikipedia.org/wiki/Markdown?links=0`);
    const body = await res.text();
    assert.equal(res.status, 200);
    assert.ok(body.includes('title: Markdown - Wikipedia') && !body.includes('## Links'));
    const bad = await fetch(`http://127.0.0.1:${port}/http://127.0.0.1/`);
    assert.equal(bad.status, 400);
  } finally { srv.kill(); }
});

test('mcp server over stdio', async () => {
  const client = new Client({ name: 'test', version: '0' });
  await client.connect(new StdioClientTransport({ command: 'node', args: [dist('mcp.js')] }));
  try {
    const tools = await client.listTools();
    assert.deepEqual(tools.tools.map((t) => t.name), ['read_url']);
    const out = await client.callTool({ name: 'read_url', arguments: { url: PAGE, links: false } });
    assert.ok(out.content[0].text.includes('useState(initialState)'));
  } finally { await client.close(); }
});

test('javascript rendering works out of the box', async () => {
  const { read, closeBrowser } = await import('../dist/index.js');
  try {
    const { markdown, result } = await read('https://react.dev/reference/react/useState', { tiers: ['chromium'] });
    assert.equal(result.tier, 'chromium');
    assert.ok(markdown.includes('useState'));
  } finally { await closeBrowser(); }
});
