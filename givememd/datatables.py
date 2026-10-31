"""Embedded-JSON collections, v2: broader candidate generation + pluggable selection.

candidates(t)   every record array in page JSON, grouped by wildcard path, records flattened
                (nested dicts -> dotted keys, so offers.price / structuredDisplayPrice... survive),
                plus repeated top-level JSON-LD objects grouped by @type (Redfin/Zillow emit one per listing).
select_rules()  cheap heuristic selection (path keywords + rows x cols), no network.
                (Jev-based selection was tested and lost to these rules: see README.)
"""
import json, re
from dataclasses import dataclass, field

SKIP_KEY = re.compile(r'^(position|employee\w*|group\w*key|tracking\w*|analytics\w*)$|(^|_)(id|url|uri|src|img|image|photo|icon|logo|href|link|hash|token|key|class|style|css|sort|rank|lat|long?|lng|zpid|pals)|^(is|has|should|show|can)[A-Z_]|Cd$|Id$|Ids$|Url$|URL$|Src$|^__typename$|^@', re.I)
SKIP_SEG = re.compile(r'logging|analytics|tracking|beacon|telemetry|experiment|^p13n|sponsored|image|picture|photo|icon|^@context$', re.I)
PREFER = ['name', 'title', 'address', 'street', 'price', 'beds', 'baths', 'area', 'sqft', 'rating', 'reviews', 'date', 'location', 'venue', 'author', 'status', 'type', 'description']
JUNK_PATH = re.compile(r'filter|facet|menu|nav|footer|header|config|setting|enum|experiment|treatment|tracking|analytics|logging|breadcrumb|i18n|locale|translation|newsletter|suggest|seo|meta(tags)?\b|^ad|[._]ads?[._]|adslot|banner|promo|mantis|consent|cookie|catalog(box)?slim|sitemenu|dynamicremotes', re.I)
MAX_RECS = 300
OPAQUE = re.compile(r'^([0-9a-f]{16,}|[A-Za-z0-9_\-=+/]{24,})$')   # hashes, tokens, base64 ids


@dataclass
class Cand:
    path: str
    recs: list                      # flattened dicts
    cols: list = field(default_factory=list)
    role: str = ''
    score: float = 0.0
    meta: dict = field(default_factory=dict)

    @property
    def rows(self): return [[fmt(r.get(c)) for c in self.cols] for r in self.recs]


ws = lambda s: re.sub(r'\s+', ' ', s).strip()


def fmt(v, limit=300):
    if v is None: return ''
    s = ws(re.sub(r'<[^>]+>', ' ', str(v))).replace('|', '/')
    return s if len(s) <= limit else s[:limit - 1] + '…'


# ---------- flattening ----------
def _scalar_list(v):
    if all(isinstance(x, (str, int, float)) and not isinstance(x, bool) for x in v):
        return ', '.join(str(x) for x in v[:6]) if v else None
    texts = []
    for x in v:
        if isinstance(x, dict):
            s = next((x[k] for k in ('text', 'body', 'name', 'label', 'title', 'value', 'discountedPrice', 'price', 'qualifier')
                      if isinstance(x.get(k), (str, int, float)) and not isinstance(x.get(k), bool)), None)
            if s is not None: texts.append(str(s))
    return ', '.join(texts[:6]) if texts else None


def flatten(o, prefix='', depth=0, out=None):
    out = {} if out is None else out
    for k, v in o.items():
        k = str(k)
        if SKIP_SEG.search(k): continue
        key = prefix + k
        if isinstance(v, dict):
            if depth < 3: flatten(v, key + '.', depth + 1, out)
        elif isinstance(v, list):
            if len(v) == 1 and isinstance(v[0], dict) and depth < 3:
                flatten(v[0], key + '.', depth + 1, out)
            else:
                s = _scalar_list(v)
                if s: out[key] = s
        elif v is not None and not isinstance(v, bool):
            out[key] = v
    return out


def unwrap(r):
    """ListItem {position, item:{...}} / GraphQL edge {node:{...}} -> the inner record."""
    for k in ('item', 'node', 'listing', 'product'):
        if isinstance(r.get(k), dict):
            inner = dict(r[k])
            for kk, vv in r.items():
                if kk != k and not isinstance(vv, (dict, list)) and kk not in inner: inner[kk] = vv
            return inner
    return r


# ---------- candidates ----------
def _scripts(t):
    for i, s in enumerate(t.css('script')):
        typ = (s.attributes.get('type') or '').lower()
        sid = s.attributes.get('id') or ''
        if 'json' in typ or typ == 'text/hydrate' or sid == '__NEXT_DATA__':
            try: yield f'{sid or typ}', typ, json.loads(s.text())
            except Exception: pass


def candidates(t):
    groups, order = {}, []

    def add(path, recs):
        if path not in groups: groups[path] = []; order.append(path)
        groups[path].extend(recs)

    def walk(o, path, depth=0):
        if depth > 14: return
        if isinstance(o, list):
            recs = [x for x in o if isinstance(x, dict)]
            if len(recs) >= 2 and len(recs) >= 0.8 * len(o):
                add(path, recs)
            for x in o[:MAX_RECS]: walk(x, path + '[]', depth + 1)
        elif isinstance(o, dict):
            for k, v in o.items():
                walk(v, path + '.' + re.sub(r'[\(:{].*', '', str(k))[:40], depth + 1)

    ld_by_type = {}
    for src, typ, j in _scripts(t):
        walk(j, src, 0)
        if 'ld+json' in typ:
            for o in (j if isinstance(j, list) else j.get('@graph', [j]) if isinstance(j, dict) else []):
                if isinstance(o, dict) and o.get('@type'):
                    ld_by_type.setdefault(str(o['@type']), []).append(o)
    # repeated top-level JSON-LD entities: join the ones describing the same thing (same url) into one record
    by_url = {}
    for typ, objs in ld_by_type.items():
        for o in objs:
            if isinstance(o.get('url'), str): by_url.setdefault(o['url'], {}).setdefault(typ, o)
    multi = {u: d for u, d in by_url.items() if len(d) >= 2}
    joined = set()
    if len(multi) >= 3:
        recs = []
        for u, d in multi.items():
            r = {}
            for typ, o in d.items():
                r.update({(k if k not in r else f'{typ}.{k}'): v for k, v in o.items()})
                joined.add(typ)
            recs.append(r)
        add('ld+json:joined-by-url', recs)
    for typ, objs in ld_by_type.items():
        if len(objs) >= 3 and typ not in joined: add(f'ld+json:{typ}', objs)

    out, seen_sets = [], set()
    for path in order:
        raw = groups[path]
        if len(raw) < 3: continue
        seen, recs = set(), []
        for r in raw:
            f = flatten(unwrap(r))
            sig = json.dumps(f, sort_keys=True, default=str)
            if f and sig not in seen:
                seen.add(sig); recs.append(f)
        sig = hash(tuple(json.dumps(r, sort_keys=True, default=str) for r in recs))
        if len(recs) >= 3 and sig not in seen_sets:          # same records under two keys (Next.js props + post content)
            seen_sets.add(sig); out.append(Cand(path, recs[:MAX_RECS]))
    return out


def all_columns(recs, min_cov=0.6):
    """Every scalar column that is filled in most records and varies."""
    n, stats, cnt = len(recs), {}, {}
    for r in recs:
        for k, v in r.items():
            last = k.split('.')[-1]
            if SKIP_KEY.search(last): continue
            if isinstance(v, str) and v.startswith(('http', '/')): continue
            stats.setdefault(k, set()).add(str(v)); cnt[k] = cnt.get(k, 0) + 1
    med = lambda k: sorted(len(x) for x in stats[k])[len(stats[k]) // 2]
    opaque = lambda k: sum(1 for x in stats[k] if OPAQUE.match(x)) >= 0.8 * len(stats[k])
    keep = [k for k in stats if cnt[k] >= min_cov * n and len(stats[k]) > 1 and med(k) <= 300 and not opaque(k)]
    low = [k.lower() for k in keep]
    keep = [k for k in keep if not (k.split('.')[-1].lower().startswith('unformatted') and
                                    k.lower().replace('unformatted', '') in [x.replace('unformatted', '') for x in low if x != k.lower()])]
    return keep


def rank_cols(cols):
    rank = lambda k: next((i for i, p in enumerate(PREFER) if p in k.split('.')[-1].lower()), len(PREFER))
    return sorted(cols, key=lambda k: (rank(k), k.count('.')))


def drop_redundant(cols, recs):
    """Drop a column whose values sit inside another column's (averageRating vs rating.averageRating,
    name vs a11y label). Of two identical columns the first is kept."""
    keep = []
    for c in cols:
        def covered(r, o):
            a, b = r.get(c), r.get(o)
            return a not in (None, '') and b not in (None, '') and str(a) in str(b) and (o in keep or len(str(b)) > len(str(a)))
        dup = sum(1 for r in recs if any(covered(r, o) for o in cols if o != c))
        if dup < 0.9 * len(recs): keep.append(c)
    return keep or cols


GENERIC_LEAF = {'value', 'text', 'amount', 'label', 'content', 'raw', 'formatted', 'display'}


def short_names(cols):
    """offers.priceSpecification.price -> price, unless two columns would collide.
    A generic leaf keeps its parent: floorSize.value -> floorSize, not 'value'."""
    out = []
    for c in cols:
        parts = c.split('.')
        if len(parts) > 1 and parts[-1].lower() in GENERIC_LEAF:
            parts = parts[:-1]
        name = parts[-1]
        i = 1
        while sum(1 for o in cols if o.split('.')[-i:] == parts[-i:]) > 1 and i < len(parts):
            i += 1; name = '.'.join(parts[-i:])
        out.append(name)
    return out


def dedupe_tables(cands):
    """Drop tables that repeat an earlier one: same rows, rows of a nested child array of an already kept
    collection (already flattened into it), or mostly the same records under another key (JSON-LD ItemList
    mirroring Next.js state)."""
    out, cells = [], []
    for c in cands:
        if any(c.path.startswith(o.path + '[]') for o in out): continue
        rows = c.rows
        first = [r[0] for r in rows if r and r[0]]
        if out and first and sum(1 for v in first if any(v in s for s in cells)) >= 0.8 * len(first) and \
                len(set(first)) > 2: continue
        out.append(c); cells.append({v for r in rows for v in r if len(v) > 3})
    return out


# ---------- selection: rules ----------
def select_rules(cands, max_tables=3, use_path_filter=True):
    keep = []
    for c in cands:
        if use_path_filter and JUNK_PATH.search(c.path): continue
        cols = rank_cols(all_columns(c.recs))[:8]
        if len(cols) < 2: continue
        c.cols = drop_redundant(cols, c.recs)
        collapse_variants(c)
        keep.append(c)
    keep.sort(key=lambda c: -len(c.recs) * len(c.cols))
    return dedupe_tables(keep)[:max_tables]


def collapse_variants(c, max_vals=6):
    """One row per item, not per colorway/size: when the first two columns repeat together, group by them and
    list the distinct values of the other columns ('Black/White; Navy; +3'). Two columns, because distinct
    items often share a generic first field ('Home in Austin') but not the second (their name)."""
    key_cols = c.cols[:2]
    keys = [tuple(str(r.get(k, '')) for k in key_cols) for r in c.recs]
    if len(c.cols) < 3 or len(set(keys)) > 0.5 * len(keys):
        return
    groups = {}
    for k, r in zip(keys, c.recs):
        groups.setdefault(k, []).append(r)
    merged = []
    for rs in groups.values():
        row = {k: rs[0].get(k) for k in key_cols}
        for col in c.cols[2:]:
            vals = list(dict.fromkeys(fmt(r.get(col)) for r in rs if r.get(col) not in (None, '')))
            row[col] = '; '.join(vals[:max_vals]) + (f'; +{len(vals) - max_vals}' if len(vals) > max_vals else '')
        merged.append(row)
    c.meta['variants'] = len(c.recs)
    c.recs = merged


def render(cands):
    blocks = []
    for c in cands:
        names = short_names(c.cols)
        if len(names) == 1:                      # a plain list (genres, sizes): one line, not a 1-column table
            vals = list(dict.fromkeys(r[0] for r in c.rows if r[0]))
            blocks.append(f'**{names[0]}** ({len(vals)}): ' + '; '.join(vals[:100])); continue
        label = f'## Data ({len(c.recs)} records)' if not c.role or c.role == 'main_content' else f'## Related ({len(c.recs)} records)'
        blocks.append(label)
        blocks.append('\n'.join(['| ' + ' | '.join(names) + ' |', '|' + '---|' * len(names)] +
                                ['| ' + ' | '.join(r) + ' |' for r in c.rows[:200]]))
    return blocks
