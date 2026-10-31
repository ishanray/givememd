/** Embedded-JSON collections (port of datatables.py): every record array in page JSON, flattened, selected by rules,
 * variants collapsed, rendered as markdown tables. Records are Maps so column order matches the Python version. */
import type { Document } from 'domhandler';
import { attr, css, text } from './dom.js';
import { isDict, isScalar, pyStr, stableStringify, uniq, ws } from './pyish.js';

const SKIP_KEY = /^(position|employee\w*|group\w*key|tracking\w*|analytics\w*)$|(^|_)(id|url|uri|src|img|image|photo|icon|logo|href|link|hash|token|key|class|style|css|sort|rank|lat|long?|lng|zpid|pals)|^(is|has|should|show|can)[A-Z_]|Cd$|Id$|Ids$|Url$|URL$|Src$|^__typename$|^@/i;
const SKIP_SEG = /logging|analytics|tracking|beacon|telemetry|experiment|^p13n|sponsored|image|picture|photo|icon|^@context$/i;
const PREFER = ['name', 'title', 'address', 'street', 'price', 'beds', 'baths', 'area', 'sqft', 'rating', 'reviews', 'date', 'location', 'venue', 'author', 'status', 'type', 'description'];
const JUNK_PATH = /filter|facet|menu|nav|footer|header|config|setting|enum|experiment|treatment|tracking|analytics|logging|breadcrumb|i18n|locale|translation|newsletter|suggest|seo|meta(tags)?\b|^ad|[._]ads?[._]|adslot|banner|promo|mantis|consent|cookie|catalog(box)?slim|sitemenu|dynamicremotes/i;
const MAX_RECS = 300;
const OPAQUE = /^([0-9a-f]{16,}|[A-Za-z0-9_\-=+/]{24,})$/;
const GENERIC_LEAF = new Set(['value', 'text', 'amount', 'label', 'content', 'raw', 'formatted', 'display']);

export type Rec = Map<string, unknown>;
export class Cand {
  cols: string[] = [];
  role = '';
  meta: Record<string, unknown> = {};
  constructor(public path: string, public recs: Rec[]) {}
  get rows(): string[][] { return this.recs.map((r) => this.cols.map((c) => fmt(r.get(c)))); }
}

export function fmt(v: unknown, limit = 300): string {
  if (v === null || v === undefined) return '';
  const s = ws(pyStr(v).replace(/<[^>]+>/g, ' ')).replaceAll('|', '/');
  return s.length <= limit ? s : s.slice(0, limit - 1) + '…';
}

function scalarList(v: unknown[]): string | null {
  if (v.every(isScalar)) return v.length ? v.slice(0, 6).map(pyStr).join(', ') : null;
  const texts: string[] = [];
  for (const x of v) {
    if (!isDict(x)) continue;
    const k = ['text', 'body', 'name', 'label', 'title', 'value', 'discountedPrice', 'price', 'qualifier'].find((k) => isScalar(x[k]));
    if (k !== undefined) texts.push(pyStr(x[k]));
  }
  return texts.length ? texts.slice(0, 6).join(', ') : null;
}

export function flatten(o: Record<string, unknown>, prefix = '', depth = 0, out: Rec = new Map()): Rec {
  for (const [k, v] of Object.entries(o)) {
    if (SKIP_SEG.test(k)) continue;
    const key = prefix + k;
    if (isDict(v)) { if (depth < 3) flatten(v, key + '.', depth + 1, out); }
    else if (Array.isArray(v)) {
      if (v.length === 1 && isDict(v[0]) && depth < 3) flatten(v[0], key + '.', depth + 1, out);
      else { const s = scalarList(v); if (s) out.set(key, s); }
    } else if (v !== null && v !== undefined && typeof v !== 'boolean') out.set(key, v);
  }
  return out;
}

function unwrap(r: Record<string, unknown>): Record<string, unknown> {
  for (const k of ['item', 'node', 'listing', 'product']) {
    if (isDict(r[k])) {
      const inner: Record<string, unknown> = { ...(r[k] as Record<string, unknown>) };
      for (const [kk, vv] of Object.entries(r)) if (kk !== k && !isDict(vv) && !Array.isArray(vv) && !(kk in inner)) inner[kk] = vv;
      return inner;
    }
  }
  return r;
}

function* scripts(doc: Document): Generator<[string, string, unknown]> {
  for (const s of css(doc, 'script')) {
    const typ = (attr(s, 'type') || '').toLowerCase();
    const sid = attr(s, 'id') || '';
    if (typ.includes('json') || typ === 'text/hydrate' || sid === '__NEXT_DATA__') {
      try { yield [sid || typ, typ, JSON.parse(text(s))]; } catch { /* not JSON */ }
    }
  }
}

export function candidates(doc: Document): Cand[] {
  const groups = new Map<string, Record<string, unknown>[]>();
  const add = (path: string, recs: Record<string, unknown>[]) => {
    if (!groups.has(path)) groups.set(path, []);
    groups.get(path)!.push(...recs);
  };
  const walk = (o: unknown, path: string, depth = 0): void => {
    if (depth > 14) return;
    if (Array.isArray(o)) {
      const recs = o.filter(isDict);
      if (recs.length >= 2 && recs.length >= 0.8 * o.length) add(path, recs);
      for (const x of o.slice(0, MAX_RECS)) walk(x, path + '[]', depth + 1);
    } else if (isDict(o)) {
      for (const [k, v] of Object.entries(o)) walk(v, path + '.' + k.replace(/[(:{].*/s, '').slice(0, 40), depth + 1);
    }
  };
  const ldByType = new Map<string, Record<string, unknown>[]>();
  for (const [src, typ, j] of scripts(doc)) {
    walk(j, src, 0);
    if (typ.includes('ld+json')) {
      const objs = Array.isArray(j) ? j : isDict(j) ? ((j['@graph'] as unknown[]) ?? [j]) : [];
      for (const o of objs) if (isDict(o) && o['@type']) {
        const t = pyType(o['@type']);
        if (!ldByType.has(t)) ldByType.set(t, []);
        ldByType.get(t)!.push(o);
      }
    }
  }
  // repeated top-level JSON-LD entities describing the same thing (same url) are joined into one record
  const byUrl = new Map<string, Map<string, Record<string, unknown>>>();
  for (const [typ, objs] of ldByType) for (const o of objs) {
    if (typeof o.url === 'string') {
      if (!byUrl.has(o.url)) byUrl.set(o.url, new Map());
      const d = byUrl.get(o.url)!;
      if (!d.has(typ)) d.set(typ, o);
    }
  }
  const multi = [...byUrl.values()].filter((d) => d.size >= 2);
  const joined = new Set<string>();
  if (multi.length >= 3) {
    const recs = multi.map((d) => {
      const r: Record<string, unknown> = {};
      for (const [typ, o] of d) {
        for (const [k, v] of Object.entries(o)) r[k in r ? `${typ}.${k}` : k] = v;
        joined.add(typ);
      }
      return r;
    });
    add('ld+json:joined-by-url', recs);
  }
  for (const [typ, objs] of ldByType) if (objs.length >= 3 && !joined.has(typ)) add(`ld+json:${typ}`, objs);

  const out: Cand[] = [];
  const seenSets = new Set<string>();
  for (const [path, raw] of groups) {
    if (raw.length < 3) continue;
    const seen = new Set<string>();
    const recs: Rec[] = [];
    for (const r of raw) {
      const f = flatten(unwrap(r));
      const sig = stableStringify(Object.fromEntries(f));
      if (f.size && !seen.has(sig)) { seen.add(sig); recs.push(f); }
    }
    const sig = recs.map((r) => stableStringify(Object.fromEntries(r))).join('\u0001');
    if (recs.length >= 3 && !seenSets.has(sig)) { seenSets.add(sig); out.push(new Cand(path, recs.slice(0, MAX_RECS))); }
  }
  return out;
}

/** Python str() of a JSON-LD @type: a list prints as "['A', 'B']". */
const pyType = (t: unknown): string => (Array.isArray(t) ? '[' + t.map((x) => `'${x}'`).join(', ') + ']' : pyStr(t));

function allColumns(recs: Rec[], minCov = 0.6): string[] {
  const n = recs.length;
  const stats = new Map<string, Set<string>>();
  const cnt = new Map<string, number>();
  for (const r of recs) for (const [k, v] of r) {
    const last = k.split('.').at(-1)!;
    if (SKIP_KEY.test(last)) continue;
    if (typeof v === 'string' && (v.startsWith('http') || v.startsWith('/'))) continue;
    if (!stats.has(k)) stats.set(k, new Set());
    stats.get(k)!.add(pyStr(v));
    cnt.set(k, (cnt.get(k) ?? 0) + 1);
  }
  const med = (k: string) => { const ls = [...stats.get(k)!].map((x) => x.length).sort((a, b) => a - b); return ls[Math.floor(ls.length / 2)]; };
  const opaque = (k: string) => [...stats.get(k)!].filter((x) => OPAQUE.test(x)).length >= 0.8 * stats.get(k)!.size;
  let keep = [...stats.keys()].filter((k) => cnt.get(k)! >= minCov * n && stats.get(k)!.size > 1 && med(k) <= 300 && !opaque(k));
  const low = keep.map((k) => k.toLowerCase());
  keep = keep.filter((k) => !(k.split('.').at(-1)!.toLowerCase().startsWith('unformatted') &&
    low.filter((x) => x !== k.toLowerCase()).map((x) => x.replaceAll('unformatted', '')).includes(k.toLowerCase().replaceAll('unformatted', ''))));
  return keep;
}

function rankCols(cols: string[]): string[] {
  const rank = (k: string) => { const i = PREFER.findIndex((p) => k.split('.').at(-1)!.toLowerCase().includes(p)); return i === -1 ? PREFER.length : i; };
  return [...cols].sort((a, b) => rank(a) - rank(b) || (a.split('.').length - b.split('.').length));
}

function dropRedundant(cols: string[], recs: Rec[]): string[] {
  const keep: string[] = [];
  for (const c of cols) {
    const covered = (r: Rec, o: string) => {
      const a = r.get(c), b = r.get(o);
      return a !== undefined && a !== null && a !== '' && b !== undefined && b !== null && b !== '' &&
        pyStr(b).includes(pyStr(a)) && (keep.includes(o) || pyStr(b).length > pyStr(a).length);
    };
    const dup = recs.filter((r) => cols.some((o) => o !== c && covered(r, o))).length;
    if (dup < 0.9 * recs.length) keep.push(c);
  }
  return keep.length ? keep : cols;
}

export function shortNames(cols: string[]): string[] {
  return cols.map((c) => {
    let parts = c.split('.');
    if (parts.length > 1 && GENERIC_LEAF.has(parts.at(-1)!.toLowerCase())) parts = parts.slice(0, -1);
    let name = parts.at(-1)!;
    let i = 1;
    const tail = (p: string[], k: number) => p.slice(-k).join('.');
    while (cols.filter((o) => tail(o.split('.'), i) === tail(parts, i)).length > 1 && i < parts.length) {
      i += 1; name = tail(parts, i);
    }
    return name;
  });
}

function dedupeTables(cands: Cand[]): Cand[] {
  const out: Cand[] = [];
  const cells: Set<string>[] = [];
  for (const c of cands) {
    if (out.some((o) => c.path.startsWith(o.path + '[]'))) continue;
    const rows = c.rows;
    const first = rows.filter((r) => r.length && r[0]).map((r) => r[0]);
    if (out.length && first.length && first.filter((v) => cells.some((s) => s.has(v))).length >= 0.8 * first.length && new Set(first).size > 2) continue;
    out.push(c);
    cells.push(new Set(rows.flat().filter((v) => v.length > 3)));
  }
  return out;
}

function collapseVariants(c: Cand, maxVals = 6): void {
  const keyCols = c.cols.slice(0, 2);
  const keys = c.recs.map((r) => keyCols.map((k) => pyStr(r.get(k) ?? '')).join('\u0001'));
  if (c.cols.length < 3 || new Set(keys).size > 0.5 * keys.length) return;
  const groups = new Map<string, Rec[]>();
  keys.forEach((k, i) => { if (!groups.has(k)) groups.set(k, []); groups.get(k)!.push(c.recs[i]); });
  const merged: Rec[] = [];
  for (const rs of groups.values()) {
    const row: Rec = new Map(keyCols.map((k) => [k, rs[0].get(k)]));
    for (const col of c.cols.slice(2)) {
      const vals = uniq(rs.filter((r) => r.get(col) !== undefined && r.get(col) !== null && r.get(col) !== '').map((r) => fmt(r.get(col))));
      row.set(col, vals.slice(0, maxVals).join('; ') + (vals.length > maxVals ? `; +${vals.length - maxVals}` : ''));
    }
    merged.push(row);
  }
  c.meta.variants = c.recs.length;
  c.recs = merged;
}

export function selectRules(cands: Cand[], maxTables = 3): Cand[] {
  const keep: Cand[] = [];
  for (const c of cands) {
    if (JUNK_PATH.test(c.path)) continue;
    const cols = rankCols(allColumns(c.recs)).slice(0, 8);
    if (cols.length < 2) continue;
    c.cols = dropRedundant(cols, c.recs);
    collapseVariants(c);
    keep.push(c);
  }
  keep.sort((a, b) => b.recs.length * b.cols.length - a.recs.length * a.cols.length);
  return dedupeTables(keep).slice(0, maxTables);
}

export function render(cands: Cand[]): string[] {
  const blocks: string[] = [];
  for (const c of cands) {
    const names = shortNames(c.cols);
    if (names.length === 1) {
      const vals = uniq(c.rows.map((r) => r[0]).filter(Boolean));
      blocks.push(`**${names[0]}** (${vals.length}): ` + vals.slice(0, 100).join('; '));
      continue;
    }
    blocks.push(!c.role || c.role === 'main_content' ? `## Data (${c.recs.length} records)` : `## Related (${c.recs.length} records)`);
    blocks.push(['| ' + names.join(' | ') + ' |', '|' + '---|'.repeat(names.length), ...c.rows.slice(0, 200).map((r) => '| ' + r.join(' | ') + ' |')].join('\n'));
  }
  return blocks;
}
