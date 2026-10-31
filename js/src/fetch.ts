/** Fetch ladder (port of fetch.py): cheapest tier first, escalate only when the page is blocked or an empty JS shell.
 *
 *   http (browser TLS fingerprint via impit, asks for text/markdown) -> lightpanda -> chromium (playwright-core)
 *
 * SSRF: every hop is resolved and refused if any address is non-public; only ports 80/443 by default; redirects are
 * followed by hand and re-checked. impit resolves names itself, so a DNS-rebinding window remains between our check
 * and its connect. GIVEMEMD_STRICT_SSRF=1 uses Node's https with the checked address pinned instead (no browser
 * fingerprint). The Python version pins with curl's RESOLVE. See SECURITY.md before running a public server. */
import { execFile } from 'node:child_process';
import { lookup } from 'node:dns/promises';
import { BlockList, isIP } from 'node:net';
import { cssFirst, attr, parse } from './dom.js';
import { BLOCKED, heuristicStatus, LOGIN_TEXT, LOGIN_URL, OK, pageStatus, type Label } from './decide.js';

const UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36';
const ACCEPT = 'text/markdown, text/html;q=0.9, application/xhtml+xml;q=0.9, */*;q=0.8';
const ALLOWED_PORTS = new Set((process.env.GIVEMEMD_ALLOWED_PORTS ?? '80,443').split(',').filter((p) => p.trim()).map(Number));
const MAX_BYTES = Number(process.env.GIVEMEMD_MAX_BYTES ?? 15_000_000);
const MAX_REDIRECTS = 5;
const CACHE_TTL = 600_000;
const cache = new Map<string, [number, Result]>();

export class UnsafeURL extends Error {}

export interface Result {
  url: string; body: string; contentType: string; tier: string; ok: boolean; trace: string[]; partial: boolean;
}
const newResult = (url: string): Result => ({ url, body: '', contentType: 'text/html', tier: '', ok: false, trace: [], partial: false });

export function normalize(target: string): string {
  let t = target.trim().replace(/^\/+/, '');
  if (!t.includes('://')) t = 'https://' + t;
  let u: URL;
  try { u = new URL(t); } catch { throw new UnsafeURL(`unsupported URL: ${t}`); }
  if ((u.protocol !== 'http:' && u.protocol !== 'https:') || !u.hostname) throw new UnsafeURL(`unsupported URL: ${t}`);
  return t;
}

// non-public ranges (Python's ipaddress is_global / is_multicast equivalent)
const PRIVATE = new BlockList();
for (const [net, bits] of [['0.0.0.0', 8], ['10.0.0.0', 8], ['100.64.0.0', 10], ['127.0.0.0', 8], ['169.254.0.0', 16], ['172.16.0.0', 12],
  ['192.0.0.0', 24], ['192.0.2.0', 24], ['192.168.0.0', 16], ['198.18.0.0', 15], ['198.51.100.0', 24], ['203.0.113.0', 24],
  ['224.0.0.0', 4], ['240.0.0.0', 4]] as const) PRIVATE.addSubnet(net, bits, 'ipv4');
// (no ::ffff:0:0/96 rule: BlockList checks IPv4 addresses against IPv6 rules in mapped form, so it would match every
// IPv4 address; mapped addresses are unwrapped and checked as IPv4 in isPublicIp instead)
for (const [net, bits] of [['::', 128], ['::1', 128], ['64:ff9b::', 96], ['100::', 64], ['2001::', 23], ['2001:db8::', 32],
  ['fc00::', 7], ['fe80::', 10], ['ff00::', 8]] as const) PRIVATE.addSubnet(net, bits, 'ipv6');

export function isPublicIp(ip: string): boolean {
  const v = isIP(ip);
  if (!v) return false;
  const mapped = ip.toLowerCase().match(/^::ffff:(\d+\.\d+\.\d+\.\d+)$/);
  if (mapped) return !PRIVATE.check(mapped[1], 'ipv4');
  return !PRIVATE.check(ip, v === 4 ? 'ipv4' : 'ipv6');
}

/** One public address for host; refuses if ANY address it resolves to is non-public. */
export async function resolvePublic(host: string): Promise<{ address: string; family: number }> {
  const h = host.replace(/^\[|\]$/g, '');
  let addrs: { address: string; family: number }[];
  try { addrs = isIP(h) ? [{ address: h, family: isIP(h) }] : await lookup(h, { all: true }); }
  catch { throw new UnsafeURL(`cannot resolve ${host}`); }
  for (const a of addrs) if (!isPublicIp(a.address)) throw new UnsafeURL(`${host} resolves to non-public address ${a.address}`);
  return addrs[0];
}

export async function checkPublic(url: string): Promise<{ address: string; family: number }> {
  const u = new URL(url);
  const port = Number(u.port) || (u.protocol === 'https:' ? 443 : 80);
  if (!ALLOWED_PORTS.has(port)) throw new UnsafeURL(`port ${port} not allowed (GIVEMEMD_ALLOWED_PORTS)`);
  return resolvePublic(u.hostname);
}

/** Bytes -> text using the header charset, then <meta charset>, then UTF-8; never throws. */
export function decode(bytes: Uint8Array, ctype = ''): string {
  const head = Buffer.from(bytes.subarray(0, 4096)).toString('latin1');
  const m = ctype.match(/charset=([\w-]+)/i) ?? head.match(/<meta[^>]+charset=["']?([\w-]+)/i);
  for (const name of [...(m ? [m[1]] : []), 'utf-8']) {
    try { return new TextDecoder(name, { fatal: true }).decode(bytes); } catch { /* next */ }
  }
  return new TextDecoder('utf-8').decode(bytes);
}

type TierOut = [status: number, body: string, ctype: string, final: string];

async function httpStrict(url: string, pinned: { address: string; family: number }): Promise<[number, Record<string, string>, Uint8Array]> {
  const mod = url.startsWith('https:') ? await import('node:https') : await import('node:http');
  return new Promise((resolve, reject) => {
    const req = mod.get(url, {
      headers: { 'User-Agent': UA, Accept: ACCEPT, 'Accept-Language': 'en-US,en;q=0.9' }, timeout: 20_000,
      lookup: (_h: string, _o: unknown, cb: (e: Error | null, a: string, f: number) => void) => cb(null, pinned.address, pinned.family),
    } as never, (res) => {
      const chunks: Buffer[] = []; let n = 0;
      res.on('data', (c: Buffer) => { n += c.length; if (n <= MAX_BYTES) chunks.push(c); else res.destroy(); });
      res.on('end', () => resolve([res.statusCode ?? 0, Object.fromEntries(Object.entries(res.headers).map(([k, v]) => [k, String(v)])), Buffer.concat(chunks)]));
      res.on('error', reject);
    });
    req.on('timeout', () => req.destroy(new Error('timeout')));
    req.on('error', reject);
  });
}

export async function tierHttp(url: string): Promise<TierOut> {
  let cur = url;
  const strict = process.env.GIVEMEMD_STRICT_SSRF === '1';
  const impit = strict ? null : new (await import('impit')).Impit({ browser: 'chrome', timeout: 20_000, followRedirects: false });
  for (let hop = 0; hop <= MAX_REDIRECTS; hop++) {
    const pinned = await checkPublic(cur);
    let status: number, headers: Record<string, string>, bytes: Uint8Array;
    if (impit) {
      const r = await impit.fetch(cur, { headers: { Accept: ACCEPT, 'Accept-Language': 'en-US,en;q=0.9' }, redirect: 'manual' });
      status = r.status; headers = Object.fromEntries(r.headers.entries());
      bytes = new Uint8Array(await r.arrayBuffer()).subarray(0, MAX_BYTES);
    } else {
      [status, headers, bytes] = await httpStrict(cur, pinned);
    }
    const loc = headers.location;
    if ([301, 302, 303, 307, 308].includes(status) && loc) { cur = normalize(new URL(loc, cur).toString()); continue; }
    const ctype = headers['content-type'] ?? '';
    return [status, decode(bytes, ctype), ctype, cur];
  }
  throw new UnsafeURL(`more than ${MAX_REDIRECTS} redirects`);
}

const LIGHTPANDA = process.env.GIVEMEMD_LIGHTPANDA;
async function tierLightpanda(url: string): Promise<TierOut> {
  if (!LIGHTPANDA) throw new Error('lightpanda not installed (set GIVEMEMD_LIGHTPANDA)');
  return new Promise((resolve) => {
    execFile(LIGHTPANDA, ['fetch', '--dump', 'html', url], { timeout: 30_000, maxBuffer: MAX_BYTES }, (err, stdout) =>
      resolve([err ? 599 : 200, stdout, 'text/html', url]));
  });
}

async function tierChromium(url: string): Promise<TierOut> {
  // optional peer dependency: loaded by name so the package builds and runs without it
  const name = 'playwright-core';
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  let pw: any;
  try { pw = await import(name); } catch { throw new Error('playwright-core not installed (npm i playwright-core && npx playwright install chromium-headless-shell)'); }
  const browser = await pw.chromium.launch({ headless: true });
  try {
    const page = await browser.newPage({ userAgent: UA, locale: 'en-US' });
    const resp = await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 30_000 });
    let status = resp ? resp.status() : 0;
    const deadline = Date.now() + 15_000;       // JS challenges solve themselves and reload; give them time
    let html = '';
    for (;;) {
      await page.waitForLoadState('networkidle', { timeout: 5_000 }).catch(() => {});
      html = await page.content();
      if (heuristicStatus(html, 200)[0] === OK || Date.now() > deadline) break;
      status = 200;
      await page.waitForTimeout(1_500);
    }
    return [status, html, 'text/html', page.url()];
  } finally {
    await browser.close();
  }
}

export function isMarkdown(body: string, ctype: string): boolean {
  const head = body.trimStart().slice(0, 500).toLowerCase();
  return !!head && (ctype.includes('markdown') || ctype.includes('text/plain')) && !['<!doctype', '<html', '<?xml', '{', '['].some((p) => head.startsWith(p));
}

export const TIERS: [string, (url: string) => Promise<TierOut>][] = [['http', tierHttp], ['lightpanda', tierLightpanda], ['chromium', tierChromium]];

/** How much a walled page still says about itself; generic login copy says nothing. */
export function metadataChars(html: string): number {
  const d = cssFirst(parse(html.slice(0, 300_000)), 'meta[name="description"], meta[property="og:description"]');
  const desc = (d && attr(d, 'content')) || '';
  return desc.length < 40 || LOGIN_TEXT.test(desc.slice(0, 80)) ? 0 : desc.length;
}

export async function fetchPage(target: string, tiers: string[] | null = null, useCache = true): Promise<Result> {
  const url = normalize(target);
  await checkPublic(url);
  const hit = cache.get(url);
  if (useCache && hit && Date.now() - hit[0] < CACHE_TTL) return { ...hit[1], tier: hit[1].tier + '+cache' };
  const res = newResult(url);
  let walled: [number, string, string, string] | null = null;
  for (const [name, fn] of TIERS) {
    if (tiers && !tiers.includes(name)) continue;
    const t0 = Date.now();
    let status: number, body: string, ctype: string, final: string;
    try { [status, body, ctype, final] = await fn(url); }
    catch (e) {
      if (e instanceof UnsafeURL) throw e;
      res.trace.push(`${name}: error ${(e as Error).name}: ${String((e as Error).message).slice(0, 80)}`); continue;
    }
    if (final !== url) await checkPublic(final);
    let label: Label, why: string;
    const path = (u: string) => { try { return new URL(u).pathname; } catch { return ''; } };
    if (status === 200 && isMarkdown(body, ctype)) { label = OK; why = 'site served markdown'; ctype = 'text/markdown'; }
    else if (LOGIN_URL.test(path(final)) && !LOGIN_URL.test(path(url))) { label = BLOCKED; why = 'redirected to login'; }
    else [label, why] = pageStatus(body, status);
    res.trace.push(`${name}: ${label} (${why}) ${((Date.now() - t0) / 1000).toFixed(1)}s`);
    if (label === OK) {
      Object.assign(res, { url: final, body, contentType: ctype, tier: name, ok: true });
      if (useCache) cache.set(url, [Date.now(), { ...res }]);
      return res;
    }
    const m = body && !LOGIN_URL.test(path(final)) ? metadataChars(body) : 0;
    if (m && (!walled || m > walled[0])) walled = [m, name, body, final];
  }
  if (walled) Object.assign(res, { tier: walled[1], body: walled[2], url: walled[3], partial: true });
  return res;
}
