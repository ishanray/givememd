/** HTML -> token-lean, fact-dense markdown (port of extract.py; component mode is Python-only for now).
 *
 *  1. metadata + JSON-LD    -> compact frontmatter
 *  2. embedded app state    -> markdown tables (see datatables.ts)
 *  3. pruned DOM            -> markdown (chrome / hidden UI / link-dense blocks removed, headlines kept)
 *  4. dedupe + clean links  -> no repeated blocks, no tracking params
 */
import type { AnyNode, Document, Element, ParentNode } from 'domhandler';
import * as datatables from './datatables.js';
import { attached, attr, body, children, css, cssFirst, hasAttr, isEl, parse, remove, replaceWith, replaceWithText, tag, text } from './dom.js';
import { alnumKey, isScalar, pyStr, uniq, wordKey, ws } from './pyish.js';

const DROP = 'script,style,noscript,svg,template,iframe,canvas,select,input,textarea,form,nav,footer,aside,dialog,link,meta,img,video,audio,picture';
const LIGHT_DROP = 'script,style,noscript,svg,template,iframe,canvas,select,input,textarea,nav,footer,dialog,link,meta,img,video,audio,picture';
const DROP_ATTR = '[aria-hidden="true"],[role="navigation"],[role="banner"],[role="contentinfo"],[role="dialog"]';
const HIDDEN = '[style*="display:none"],[style*="display: none"]';
const BUTTON_LABEL = 25;
export const UI_TEXT = /^(- )?(loading\.*|image (un)?available|image not available( for)?:?|videos?|images|360° view|(brief|full) content visible.*|sign in to continue|skip to (main )?content|show (more|less)|see (more|less)|read more|view all|advertisement|sponsored|back to top|(color|size|style):)\.?$/i;
const CARD_TAGS = new Set(['li', 'article', 'div', 'section']);
const DATA_MARK = 'GIVEMEMDDATA';
const REVEAL = /expander|collaps|accordion|tab-?panel|read-?more|see-?more|truncat/i;
const BLOCK = new Set(['p', 'div', 'section', 'article', 'main', 'header', 'ul', 'ol', 'li', 'table', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'pre', 'blockquote', 'dl', 'dt', 'dd', 'figure', 'figcaption', 'hr', 'br', 'body', 'center', 'details', 'summary', 'tbody', 'thead']);
const TRACKING = /^(utm_|ref_?$|pd_rd|pf_rd|content-id|_encoding|psc$|qid$|sr$|crid$|sprefix|dib|th$|trk|fbclid|gclid|mc_|_ga)/i;
const RC_CALL = /\$R[CS]\(\s*"([^"]+)"\s*,\s*"([^"]+)"/g;
const HIDE_CLASS = /(^|\s)(w-form-fail|w-form-done)(\s|$)/;
const SHOWN_AT = /(^|\s)(sm|md|lg|xl|2xl):(block|flex|grid|inline|inline-block|table|contents)(\s|$)|(^|\s)d-(sm|md|lg|xl)-(block|flex|inline)/;
const HEADLINE_MARK = '⁣';
// Inline elements are padded with a soft space so '<b>A</b><b>B</b>' reads 'A B'. The pad is dropped next to
// punctuation the page wrote directly against the element: '<em>it</em>.' -> 'it.', '(<a>x</a>)' -> '(x)'.
const SOFT = '\x01';
const SOFT_BEFORE = /\x01+(?=[.,;:!?)\]}%]|['\u2019]s(?![\p{L}\p{N}_]))/gu;
const SOFT_AFTER = /(?<=[(\[{])\x01+/gu;
const unsoft = (s: string): string => s.replace(SOFT_BEFORE, '').replace(SOFT_AFTER, '').replaceAll(SOFT, ' ');
const itext = (n: AnyNode): string => ws(unsoft(text(n, SOFT)));   // an element's text as one rendered line
const HEADLINE_WORDS = 4, HEADLINE_MAX = 30;
const OUTSIDE_SKIP = 'nav,footer,aside,header,form,dialog,[role="dialog"],[role="navigation"],[role="banner"],[role="contentinfo"],[aria-hidden="true"]';

export function cleanUrl(href: string, base: string): string | null {
  let u: URL;
  try { u = new URL(href, base); } catch { return null; }
  if (u.protocol !== 'http:' && u.protocol !== 'https:') return null;
  const q = new URLSearchParams([...u.searchParams].filter(([k]) => !TRACKING.test(k))).toString();
  const path = u.pathname.replace(/\/ref=[^/]*$/, '');
  return `${u.protocol}//${u.host}${path}${q ? '?' + q : ''}`;
}

// ---------- layer 1: metadata ----------
function frontmatter(doc: Document, url: string): Record<string, string> {
  const m: Record<string, string> = {};
  const title = cssFirst(doc, 'title');
  if (title) m.title = ws(text(title));
  for (const [sel, k] of [['meta[name="description"]', 'description'], ['meta[property="og:description"]', 'description'], ['link[rel="canonical"]', 'url']]) {
    const n = cssFirst(doc, sel);
    const v = n && (attr(n, 'content') || attr(n, 'href'));
    if (v && !(k in m)) m[k] = ws(v);
  }
  if (!('url' in m)) m.url = url;
  return m;
}

function jsonld(doc: Document): Record<string, unknown>[] {
  const out: Record<string, unknown>[] = [];
  for (const s of css(doc, 'script[type="application/ld+json"]')) {
    let d: unknown;
    try { d = JSON.parse(text(s)); } catch { continue; }
    const items = Array.isArray(d) ? d : d && typeof d === 'object' ? ((d as Record<string, unknown>)['@graph'] as unknown[]) ?? [d] : [];
    for (const o of items) if (o && typeof o === 'object' && !Array.isArray(o)) out.push(o as Record<string, unknown>);
  }
  return out;
}

// ---------- layer 3: DOM -> markdown ----------
/** React 18 streaming SSR: late content arrives as <div hidden id="S:n"> + $RC("B:m","S:n"); do the move ourselves. */
export function unstream(doc: Document): void {
  const scripts = css(doc, 'script').map((s) => text(s)).filter((t) => t.includes('$R')).join(' ');
  const moves = new Map<string, string>();
  for (const m of scripts.matchAll(RC_CALL)) moves.set(m[2], m[1]);
  for (const seg of css(doc, 'div[hidden][id^="S:"]')) {
    const sid = attr(seg, 'id')!;
    delete seg.attribs.hidden;
    const b = moves.get(sid);
    const tpl = b ? cssFirst(doc, `template[id="${b}"]`) : null;
    if (tpl) replaceWith(tpl, seg);
  }
}

function stats(n: Element): [string, number, number] {
  const t = ws(text(n, ' '));
  const links = css(n, 'a');
  return [t, links.length, links.reduce((s, a) => s + ws(text(a, ' ')).length, 0) / Math.max(t.length, 1)];
}

function under(n: AnyNode, ids: Set<AnyNode>): boolean {
  for (let p = n.parent; p; p = p.parent) if (ids.has(p)) return true;
  return false;
}

/** Link texts in a link-dense block that read like headlines or product names (4+ words), not menu labels. */
function headlines(n: Element): string[] {
  const out: string[] = [];
  for (const a of css(n, 'a')) {
    const t = itext(a);
    if (t.split(/\s+/u).filter(Boolean).length >= HEADLINE_WORDS && t.length <= 160 && !UI_TEXT.test(t) && !out.includes(t)) out.push(t);
  }
  return out.length >= 2 ? out.slice(0, HEADLINE_MAX) : [];
}

function prune(root: Element, light = false): void {
  for (const n of css(root, (light ? LIGHT_DROP : DROP) + ',' + DROP_ATTR)) remove(n);
  for (const n of css(root, 'button')) if (ws(text(n, ' ')).length <= BUTTON_LABEL) remove(n);
  for (const n of css(root, '[class]')) {
    const cls = attr(n, 'class') || '';
    if (HIDE_CLASS.test(cls) && !SHOWN_AT.test(cls) && !REVEAL.test(cls)) remove(n);
  }
  for (const n of css(root, HIDDEN)) {
    const parentCls = n.parent && isEl(n.parent) ? attr(n.parent, 'class') || '' : '';
    if (!REVEAL.test((attr(n, 'class') || '') + ' ' + parentCls)) remove(n);
  }
  if (light) return;
  const dropped: Element[] = [];
  const ids = new Set<AnyNode>();
  for (const n of css(root, 'div,ul,ol,section,table,header')) {
    if (!n.parent || under(n, ids)) continue;
    const [t, nl, dens] = stats(n);
    if (t.length < 1) { remove(n); continue; }
    if (nl >= 6 && dens > 0.6) { dropped.push(n); ids.add(n); }
  }
  for (const n of dropped) {
    const heads = headlines(n);
    if (heads.length) replaceWithText(n, HEADLINE_MARK + heads.join(' · ') + HEADLINE_MARK);
    else remove(n);
  }
}

class MD {
  static MAX_DEPTH = 200;
  blocks: string[] = [];
  buf: string[] = [];
  links: [string, string][] = [];
  depth = 0;
  headlineChars = 0;
  headlineBlocks = new Set<number>();
  constructor(public base: string) {}

  flush(prefix = ''): void {
    const s = ws(unsoft(this.buf.join('')));
    this.buf = [];
    if (s.includes(HEADLINE_MARK)) {
      s.split(HEADLINE_MARK).forEach((raw, i) => {
        const part = raw.trim();
        if (!part) return;
        this.blocks.push(i % 2 ? part : prefix + part);
        if (i % 2) { this.headlineChars += part.length; this.headlineBlocks.add(this.blocks.length - 1); }
      });
      return;
    }
    if (s) this.blocks.push(prefix + s);
  }

  walk(n: ParentNode, listDepth = 0): void {
    if (this.depth >= MD.MAX_DEPTH) { this.buf.push(SOFT + text(n, SOFT) + SOFT); return; }
    this.depth += 1;
    try { for (const c of children(n)) this.handle(c, listDepth); } finally { this.depth -= 1; }
  }

  handle(c: AnyNode, listDepth = 0): void {
    const t = tag(c);
    if (t === '-text') { this.buf.push((c as unknown as { data: string }).data); return; }
    if (t === '-other') return;
    const el = c as Element;
    if (/^h[1-6]$/.test(t)) {
      this.flush(); const s = itext(el);
      if (s) this.blocks.push('#'.repeat(Number(t[1])) + ' ' + s);
    } else if (t === 'pre') {
      this.flush(); this.blocks.push('```\n' + text(el).replace(/^\n+|\n+$/g, '') + '\n```');
    } else if (t === 'table') {
      this.flush(); this.table(el);
    } else if (t === 'li') {
      this.flush(); const start = this.blocks.length; const prefix = '  '.repeat(Math.max(listDepth - 1, 0)) + '- ';
      this.walk(el, listDepth); this.flush(prefix); this.mergeCard(start, prefix);
    } else if (t === 'ul' || t === 'ol') {
      this.flush(); this.walk(el, listDepth + 1); this.flush();
    } else if (t === 'a') {
      const s = itext(el);
      const href = attr(el, 'href');
      const u = href ? cleanUrl(href, this.base) : null;
      if (s && u && s.length > 3) this.links.push([s, u]);
      this.buf.push(SOFT + s + SOFT);
    } else if (t === 'code') {
      const s = text(el);
      this.buf.push(s.trim() ? '`' + s + '`' : '');
    } else if (BLOCK.has(t)) {
      this.flush(); const start = this.blocks.length;
      this.walk(el, listDepth); this.flush();
      if (CARD_TAGS.has(t)) this.mergeCard(start);
    } else {
      this.buf.push(SOFT); this.walk(el, listDepth); this.buf.push(SOFT);
    }
  }

  /** '$449,000' / '- 4 bds' / '- 3 ba' / '8709 Blaze Dr' -> one line joined with ' · ' (3-12 short plain lines only). */
  mergeCard(start: number, prefix = ''): void {
    const part = this.blocks.slice(start);
    if (part.length < 3 || part.length > 12) return;
    if (part.some((b) => b.length > 60 || b.startsWith('#') || b.startsWith('```') || b.startsWith('|') || b.includes(DATA_MARK))) return;
    if (part.filter((b) => b.includes(': ')).length > part.length / 2) return;
    const items = part.filter((b) => !UI_TEXT.test(b)).map((b) => b.replace(/^\s*- /, ''));
    this.blocks.splice(start, this.blocks.length - start, ...(items.length ? [prefix + items.join(' · ')] : []));
  }

  table(tbl: Element): void {
    let rows = css(tbl, 'tr').map((tr) => css(tr, 'th,td').map((td) => itext(td).replaceAll('|', '/')));
    rows = rows.filter((r) => r.some(Boolean));
    if (!rows.length) return;
    const w = Math.max(...rows.map((r) => r.length));
    if (w === 2) { this.blocks.push(...rows.map((r) => (r.length === 2 ? `- ${r[0]}: ${r[1]}` : `- ${r[0]}`))); return; }
    rows = rows.map((r) => [...r, ...Array(w - r.length).fill('')]);
    this.blocks.push(['| ' + rows[0].join(' | ') + ' |', '|' + '---|'.repeat(w), ...rows.slice(1).map((r) => '| ' + r.join(' | ') + ' |')].join('\n'));
  }
}

/** Drop headline items already present elsewhere on the page; a line left with fewer than two items goes. */
function trimHeadlines(md: MD): void {
  if (!md.headlineBlocks.size) return;
  const other = md.blocks.filter((_, i) => !md.headlineBlocks.has(i)).map(wordKey).join(' ');
  for (const i of [...md.headlineBlocks].sort((a, b) => a - b)) {
    const items = md.blocks[i].split(' · ').filter((h) => !other.includes(wordKey(h)));
    md.blocks[i] = items.length >= 2 ? items.join(' · ') : '';
  }
  md.blocks = md.blocks.filter(Boolean);
  md.headlineBlocks = new Set();
}

function dedupe(blocks: string[]): string[] {
  const seen = new Set<string>();
  const out: string[] = [];
  for (const b of blocks) {
    const k = alnumKey(b);
    // h4+ headings like "#### Image Unavailable" are UI; an h1-h3 named "Videos" is a real section
    if (k.length < 2 || seen.has(k) || (!/^#{1,3} /.test(b) && UI_TEXT.test(b.replace(/^#+ /, '')))) continue;
    seen.add(k); out.push(b);
  }
  return out;
}

function compactMeta(meta: Record<string, string>): Record<string, string> {
  const m = { ...meta };
  if ('description' in m && 'title' in m) {
    const d = alnumKey(m.description), t = alnumKey(m.title);
    if (t.includes(d) || d.includes(t)) delete m.description;
  }
  return m;
}

const pyType = (t: unknown): string => (Array.isArray(t) ? '[' + t.map((x) => `'${x}'`).join(', ') + ']' : pyStr(t));

function ldLines(ld: Record<string, unknown>[], meta: Record<string, string>): string[] {
  const known = new Set(Object.entries(meta).filter(([k]) => k === 'title' || k === 'description').map(([, v]) => alnumKey(v)));
  const byType = new Map<string, Record<string, unknown>[]>();
  for (const o of ld) if (o['@type']) {
    const t = pyType(o['@type']);
    if (!byType.has(t)) byType.set(t, []);
    byType.get(t)!.push(o);
  }
  const lines: string[] = [];
  for (const [typ, objs] of byType) {
    const flats: Map<string, string>[] = [];
    for (const o of objs) {
      const flat = new Map<string, string>();
      for (const [k, v] of Object.entries(o)) {
        if (k.startsWith('@') || !isScalar(v)) continue;
        const s = pyStr(v);
        if (s.startsWith('http') || s.length >= 200 || known.has(alnumKey(s))) continue;
        flat.set(k, ws(s));
      }
      if (flat.size && !(flat.size === 1 && flat.has('name'))) flats.push(flat);
    }
    if (flats.length >= 3) {
      const names = flats.map((f) => f.get('name') || f.get('headline') || '').filter(Boolean);
      if (names.length) // a bare count ("ImageObject (4): ; …") tells a model nothing
        lines.push(`${typ} (${flats.length}): ` + names.slice(0, 3).join('; ') + (flats.length > 3 ? '; …' : ''));
    } else {
      for (const f of flats) lines.push(`${typ}: ` + [...f].slice(0, 8).map(([k, v]) => `${k}=${v}`).join('; '));
    }
  }
  return lines;
}

/** Swap the rendered listing grid that the top data table describes for a marker, so the table appears once, in place. */
function replaceGrid(root: Element, cand: datatables.Cand): Element | null {
  const rows = cand.rows;
  const keys = uniq(rows.map((r) => r[0]).filter((k) => k.length >= 6));
  if (keys.length < 3) return null;
  const cells = new Set(rows.flat().filter((v) => v.length >= 3));
  const score = (n: Element): [number, string] => { const t = ws(text(n, ' ')); return [keys.filter((k) => t.includes(k)).length, t]; };
  const [total] = score(root);
  if (total < 3) return null;
  let best: [Element, string] | null = null;
  for (const n of css(root, 'div,ul,ol,section,table')) {
    const [hits, t] = score(n);
    if (hits >= Math.max(3, 0.8 * total) && (!best || t.length < best[1].length)) best = [n, t];
  }
  if (!best) return null;
  const [n, t] = best;
  const covered = [...cells].filter((v) => t.includes(v)).reduce((s, v) => s + v.length, 0);
  if (covered < 0.25 * t.length) return null;
  replaceWithText(n, DATA_MARK);
  return n;
}

/** Prose outside <main> (paragraphs of 60+ chars, headings over them) that isn't link-dense or in a chrome region. */
function outsideProse(doc: Document, root: Element, md: MD): void {
  const b = body(doc);
  if (!b) return;
  const skip = new Set<AnyNode>(css(b, OUTSIDE_SKIP));
  const seen = new Set(md.blocks.map((x) => x.toLowerCase().replace(/[^\p{L}\p{N}_]+/gu, ' ')));
  const chrome = (n: AnyNode) => { for (let p: AnyNode | null = n; p; p = p.parent) if (skip.has(p) || p === root) return true; return false; };
  for (const n of css(b, 'p,h2,h3')) {
    const t = ws(text(n, ' '));
    if (t.length < (n.name === 'p' ? 60 : 15) || chrome(n)) continue;
    const linkChars = css(n, 'a').reduce((s, a) => s + ws(text(a, ' ')).length, 0);
    if (linkChars > 0.3 * t.length) continue;
    const key = t.toLowerCase().replace(/[^\p{L}\p{N}_]+/gu, ' ');
    if (seen.has(key)) continue;
    seen.add(key);
    md.blocks.push(n.name !== 'p' ? '#'.repeat(Number(n.name[1])) + ' ' + t : t);
  }
}

/** <main> / role=main / <article> only when it holds at least 75% of the body's text outside menus and footers. */
function mainRoot(doc: Document): Element | null {
  const b = body(doc);
  if (!b) return null;
  const size = (n: Element) => text(n, ' ').length - css(n, 'script,style,noscript,nav,footer,header').reduce((s, x) => s + text(x, ' ').length, 0);
  const total = size(b);
  for (const sel of ['main', '[role="main"]', 'article']) {
    const n = cssFirst(doc, sel);
    if (n && text(n).length > 500 && size(n) >= 0.75 * total) return n;
  }
  return b;
}

export interface ConvertOptions { links?: boolean; metaOnly?: boolean; mode?: 'portal' | null }

export function convert(html: string, url: string, opts: ConvertOptions = {}): string {
  const { links = true, metaOnly = false, mode = null } = opts;
  const doc = parse(html);
  unstream(doc);
  const meta = frontmatter(doc, url);
  const ld = jsonld(doc);
  const cands = datatables.selectRules(datatables.candidates(doc));
  const md = new MD(url);
  let grid: Element | null = null;
  if (!metaOnly) {
    const root = mainRoot(doc);
    if (root) {
      const before = mode !== 'portal' ? ws(text(root, ' ')).length : 0;
      prune(root, mode === 'portal');
      grid = cands.length ? replaceGrid(root, cands[0]) : null;
      md.walk(root); md.flush();
      if (root !== body(doc)) outsideProse(doc, root, md);
      trimHeadlines(md);
      const kept = md.blocks.reduce((s, x) => s + x.length, 0) - md.headlineChars;
      if (mode === null && kept < 2000 && kept < 0.25 * before) {
        // a portal / homepage: the link lists ARE the content, and link-density pruning removed nearly everything
        return convert(html, url, { links, mode: 'portal' });
      }
    }
  }
  const out = ['---', ...Object.entries(compactMeta(meta)).map(([k, v]) => `${k}: ${v}`), ...ldLines(ld, meta)];
  if (metaOnly) out.push('partial: the site showed a login wall or block page; only its metadata and embedded data are included');
  out.push('---');
  let blocks = dedupe(md.blocks);
  let tables = cands.map((c) => datatables.render([c]));
  const at = blocks.findIndex((b) => b.includes(DATA_MARK));
  if (grid && at !== -1) {
    const rest = blocks[at].replace(DATA_MARK, '').trim();
    blocks.splice(at, 1, ...(rest ? [rest] : []), ...tables[0]);
    tables = tables.slice(1);
  } else {
    blocks = blocks.map((b) => b.replace(DATA_MARK, '').trim()).filter(Boolean);
  }
  blocks.push(...tables.flat());
  if (links) {
    const seen = new Set<string>();
    const L: string[] = [];
    for (const [s, u] of md.links) {
      if (!seen.has(u) && u.replace(/\/+$/, '') !== url.replace(/\/+$/, '')) { seen.add(u); L.push(`- [${ws(s).slice(0, 60)}](${u})`); }
    }
    if (L.length) blocks.push('## Links\n' + L.slice(0, 25).join('\n'));
  }
  return out.join('\n') + '\n\n' + blocks.join('\n\n') + '\n';
}

export { attached, hasAttr };
