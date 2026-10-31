"""givememd extractor: HTML -> token-lean, fact-dense markdown for LLMs.

Layers:
  1. metadata + JSON-LD          -> compact frontmatter
  2. embedded app state          -> markdown tables (data the DOM lazy-loads; see datatables.py)
  3. pruned DOM                  -> markdown (link-dense / hidden / chrome removed; optional Jev rescue)
  4. dedupe + clean links        -> no repeated blocks, no tracking params
"""
import json, os, re, sys
from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from selectolax.lexbor import LexborHTMLParser

from . import datatables, jev

DROP = 'script,style,noscript,svg,template,iframe,canvas,select,input,textarea,form,nav,footer,aside,dialog,link,meta,img,video,audio,picture'
BUTTON_LABEL = 25               # a <button> with more text than this holds content (card title, FAQ question), not a label
DROP_ATTR = '[aria-hidden="true"],[role="navigation"],[role="banner"],[role="contentinfo"],[role="dialog"]'
HIDDEN = '[style*="display:none"],[style*="display: none"]'
HEADINGS = 'h1,h2,h3,h4'
# interface microcopy that carries no page facts (a whole block must match)
UI_TEXT = re.compile(r'^(- )?(loading\.*|image (un)?available|image not available( for)?:?|videos?|images|360° view|'
                     r'(brief|full) content visible.*|sign in to continue|skip to (main )?content|show (more|less)|'
                     r'see (more|less)|read more|view all|advertisement|sponsored|back to top|(color|size|style):)\.?$', re.I)
CARD_TAGS = {'li', 'article', 'div', 'section'}
DATA_MARK = 'GIVEMEMDDATA'
MAX_RESCUE = 20                 # bounds Jev cost per page
REVEAL = re.compile(r'expander|collaps|accordion|tab-?panel|read-?more|see-?more|truncat', re.I)
BLOCK = {'p', 'div', 'section', 'article', 'main', 'header', 'ul', 'ol', 'li', 'table', 'tr', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
         'pre', 'blockquote', 'dl', 'dt', 'dd', 'figure', 'figcaption', 'hr', 'br', 'body', 'center', 'details', 'summary', 'tbody', 'thead'}
TRACKING = re.compile(r'^(utm_|ref_?$|pd_rd|pf_rd|content-id|_encoding|psc$|qid$|sr$|crid$|sprefix|dib|th$|trk|fbclid|gclid|mc_|_ga)', re.I)

ws = lambda s: re.sub(r'\s+', ' ', s).strip()


def clean_url(href, base):
    u = urlsplit(urljoin(base, href))
    if u.scheme not in ('http', 'https'): return None
    q = [(k, v) for k, v in parse_qsl(u.query) if not TRACKING.match(k)]
    path = re.sub(r'/ref=[^/]*$', '', u.path)
    return urlunsplit((u.scheme, u.netloc, path, urlencode(q), ''))


# ---------- layer 1: metadata ----------
def frontmatter(t, url):
    m = {}
    if t.css_first('title'): m['title'] = ws(t.css_first('title').text())
    for sel, k in [('meta[name="description"]', 'description'), ('meta[property="og:description"]', 'description'),
                   ('link[rel="canonical"]', 'url')]:
        n = t.css_first(sel)
        v = n and (n.attributes.get('content') or n.attributes.get('href'))
        if v and k not in m: m[k] = ws(v)
    m.setdefault('url', url)
    return m


def jsonld(t):
    out = []
    for s in t.css('script[type="application/ld+json"]'):
        try: d = json.loads(s.text())
        except Exception: continue
        for o in (d.get('@graph', [d]) if isinstance(d, dict) else d):
            if isinstance(o, dict): out.append(o)
    return out


# ---------- layer 3: DOM -> markdown ----------
LIGHT_DROP = 'script,style,noscript,svg,template,iframe,canvas,select,input,textarea,nav,footer,dialog,link,meta,img,video,audio,picture'


RC_CALL = re.compile(r'\$R[CS]\(\s*"([^"]+)"\s*,\s*"([^"]+)"')
# only classes that always mean a status message; generic ones (hidden, d-none) are toggled by JS for tabs and
# accordions and hid real content (a recipe's nutrition panel, a product comparison) when tried
HIDE_CLASS = re.compile(r'(^|\s)(w-form-fail|w-form-done)(\s|$)')
SHOWN_AT = re.compile(r'(^|\s)(sm|md|lg|xl|2xl):(block|flex|grid|inline|inline-block|table|contents)(\s|$)|(^|\s)d-(sm|md|lg|xl)-(block|flex|inline)')


def unstream(t):
    """React 18 streaming SSR sends late content as <div hidden id="S:n"> plus a script $RC("B:m","S:n") that moves it
    into <template id="B:m">. Do that move ourselves; otherwise the content looks hidden and is thrown away."""
    html_scripts = ' '.join(s.text() for s in t.css('script') if '$R' in s.text())
    moves = dict((seg, boundary) for boundary, seg in RC_CALL.findall(html_scripts))
    for seg in t.css('div[hidden][id^="S:"]'):
        sid = seg.attributes.get('id')
        if 'hidden' in seg.attributes:
            del seg.attrs['hidden']
        tpl = t.css_first(f'template[id="{moves.get(sid, "")}"]') if sid in moves else None
        if tpl is not None:
            tpl.replace_with(seg)


def prune(root, judge=None, title='', light=False):
    """Drop chrome. With a Jev judge, link-dense blocks that carry a heading ("See also", a list article)
    are re-asked and kept if Jev calls them content; any Jev failure falls back to the heuristic.
    light: only drop what is never content (scripts, hidden, nav, footer) and keep forms, asides and link-dense
    blocks, so section labels decide what is junk (component mode)."""
    for n in root.css((LIGHT_DROP if light else DROP) + ',' + DROP_ATTR):
        n.decompose()
    for n in root.css('button'):
        if len(ws(n.text(separator=' '))) <= BUTTON_LABEL:
            n.decompose()
    # form status messages ("Oops! Something went wrong while submitting the form")
    for n in root.css('[class]'):
        cls = n.attributes.get('class') or ''
        if HIDE_CLASS.search(cls) and not SHOWN_AT.search(cls) and not REVEAL.search(cls):
            n.decompose()
    # display:none is junk (modals, templates) unless it's collapsed real content ("see more", tabs)
    for n in root.css(HIDDEN):
        if not REVEAL.search((n.attributes.get('class') or '') + ' ' + (n.parent.attributes.get('class') or '' if n.parent else '')):
            n.decompose()
    if light:
        return
    # link-dense containers are navigation / carousels / footers
    dropped, ids = [], set()
    for n in list(root.css('div,ul,ol,section,table,header')):
        if n.parent is None or _under(n, ids): continue
        text, nl, dens = _stats(n)
        if len(text) < 1: n.decompose(); continue
        if nl >= 6 and dens > 0.6:
            dropped.append(n); ids.add(n.mem_id)
    if judge:
        dropped = _rescue(root, judge, dropped, title)
    for n in dropped:
        heads = headlines(n)
        if heads:                      # story/product cards: keep the headlines as one compact line, drop the menu
            n.replace_with(HEADLINE_MARK + ' · '.join(heads) + HEADLINE_MARK)
        else:
            n.decompose()


HEADLINE_MARK = '\u2063'             # invisible separator: the line becomes its own block (see MD.flush)
HEADLINE_WORDS, HEADLINE_MAX = 4, 30


def trim_headlines(md):
    """Drop headline items already present elsewhere on the page (as a heading or in a teaser); a line left with
    fewer than two items goes."""
    if not md.headline_blocks: return
    key = lambda x: re.sub(r'\W+', ' ', x.lower()).strip()
    other = ' '.join(key(b) for i, b in enumerate(md.blocks) if i not in md.headline_blocks)
    for i in sorted(md.headline_blocks):
        items = [h for h in md.blocks[i].split(' · ') if key(h) not in other]
        md.blocks[i] = ' · '.join(items) if len(items) >= 2 else ''
    md.blocks = [b for b in md.blocks if b]
    md.headline_blocks = set()


def headlines(n):
    """Link texts in a link-dense block that read like headlines or product names (4+ words), not menu labels."""
    out = []
    for a in n.css('a'):
        t = ws(a.text(separator=' '))
        if len(t.split()) >= HEADLINE_WORDS and len(t) <= 160 and not UI_TEXT.match(t) and t not in out:
            out.append(t)
    return out[:HEADLINE_MAX] if len(out) >= 2 else []


def _stats(n):
    text = ws(n.text(separator=' '))
    links = n.css('a')
    return text, len(links), sum(len(ws(a.text(separator=' '))) for a in links) / max(len(text), 1)


def _under(n, ids):
    p = n.parent
    while p is not None:
        if p.mem_id in ids: return True
        p = p.parent
    return False


def _describe(n, text, nl, dens, limit=600):
    tag = n.tag + ''.join('.' + c for c in (n.attributes.get('class') or '').split()[:3]) + ('#' + n.attributes['id'] if n.attributes.get('id') else '')
    h = n.css_first(HEADINGS)
    head = f' heading "{ws(h.text())[:80]}"' if h else ''
    body = text if len(text) <= limit else text[:limit - 150] + ' ... ' + text[-150:]
    return f'<{tag[:80]}>{head} [{nl} links, {dens:.0%} link text, {len(text)} chars]\n{body}'


def _rescue(root, judge, dropped, title):
    ask = [n for n in dropped if n.css_first(HEADINGS)][:MAX_RESCUE]
    if not ask: return dropped
    outline = [ws(h.text())[:80] for h in root.css('h1,h2,h3')][:60]
    state = f'Web page: {title}\nOutline (headings in page order): ' + ' | '.join(o for o in outline if o)
    probs = judge.classify(state, [_describe(n, *_stats(n)) for n in ask])
    if probs is None: return dropped                       # fail open to the heuristic
    rescued = {n.mem_id for n, p in zip(ask, probs) if jev.keep_prob(p) >= 0.5}
    return [n for n in dropped if n.mem_id not in rescued]


class MD:
    MAX_DEPTH = 200                # some pages nest thousands of elements; below this depth, take plain text

    def __init__(self, base):
        self.base, self.blocks, self.buf, self.links = base, [], [], []
        self.depth = 0
        self.headline_chars = 0       # text that came from compacted headline lists (not counted as 'kept' content)
        self.headline_blocks = set()  # their block indexes, so repeats can be trimmed once the page is assembled

    def flush(self, prefix=''):
        s = ws(''.join(self.buf))
        self.buf = []
        if HEADLINE_MARK in s:         # a compacted headline line always stands alone
            for i, part in enumerate(s.split(HEADLINE_MARK)):
                part = part.strip()
                if part:
                    self.blocks.append(part if i % 2 else prefix + part)
                    if i % 2: self.headline_chars += len(part); self.headline_blocks.add(len(self.blocks) - 1)
            return
        if s: self.blocks.append(prefix + s)

    def walk(self, n, list_depth=0):
        if self.depth >= self.MAX_DEPTH:
            self.buf.append(' ' + n.text(separator=' ') + ' ')
            return
        self.depth += 1
        try:
            for c in n.iter(include_text=True):
                self.handle(c, list_depth)
        finally:
            self.depth -= 1

    def handle(self, c, list_depth=0):
            """Render one node (element or text) into the current blocks."""
            tag = c.tag
            if tag == '-text':
                self.buf.append(c.text(deep=False)); return
            if tag == '-comment':       # React's <!-- --> text separators: no space ("29<!-- -->g" renders as "29g")
                return
            if tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                self.flush(); s = ws(c.text(separator=' '))
                if s: self.blocks.append('#' * int(tag[1]) + ' ' + s)
            elif tag == 'pre':
                self.flush(); self.blocks.append('```\n' + c.text().strip('\n') + '\n```')
            elif tag == 'table':
                self.flush(); self.table(c)
            elif tag == 'li':
                self.flush(); start = len(self.blocks)
                self.walk(c, list_depth); self.flush('  ' * max(list_depth - 1, 0) + '- ')
                self.merge_card(start, '  ' * max(list_depth - 1, 0) + '- ')
            elif tag in ('ul', 'ol'):
                self.flush(); self.walk(c, list_depth + 1); self.flush()
            elif tag == 'a':
                s = ws(c.text(separator=' '))
                href = c.attributes.get('href')
                u = href and clean_url(href, self.base)
                if s and u and len(s) > 3: self.links.append((s, u))
                self.buf.append(' ' + s + ' ')
            elif tag == 'code':
                s = c.text()
                self.buf.append(f'`{s}`' if s.strip() else '')
            elif tag in BLOCK:
                self.flush(); start = len(self.blocks)
                self.walk(c, list_depth); self.flush()
                if tag in CARD_TAGS: self.merge_card(start)
            else:
                self.buf.append(' '); self.walk(c, list_depth); self.buf.append(' ')

    def merge_card(self, start, prefix=''):
        """'$449,000' / '- 4 bds' / '- 3 ba' / '8709 Blaze Dr' -> '$449,000 · 4 bds · 3 ba · 8709 Blaze Dr'.
        Only for 3-12 short plain lines; key/value lists, headings, code and tables stay as they are."""
        part = self.blocks[start:]
        if not 3 <= len(part) <= 12: return
        if any(len(b) > 60 or b.startswith(('#', '```', '|')) or DATA_MARK in b for b in part): return
        if sum(1 for b in part if ': ' in b) > len(part) / 2: return
        items = [re.sub(r'^\s*- ', '', b) for b in part if not UI_TEXT.match(b)]
        self.blocks[start:] = [prefix + ' · '.join(items)] if items else []

    def table(self, tbl):
        rows = [[ws(td.text(separator=' ')).replace('|', '/') for td in tr.css('th,td')] for tr in tbl.css('tr')]
        rows = [r for r in rows if any(r)]
        if not rows: return
        if max(len(r) for r in rows) == 2:          # key/value table -> compact lines
            self.blocks.extend(f'- {r[0]}: {r[1]}' if len(r) == 2 else f'- {r[0]}' for r in rows)
            return
        w = max(len(r) for r in rows)
        rows = [r + [''] * (w - len(r)) for r in rows]
        self.blocks.append('\n'.join(['| ' + ' | '.join(rows[0]) + ' |', '|' + '---|' * w] +
                                     ['| ' + ' | '.join(r) + ' |' for r in rows[1:]]))


def dedupe(blocks):
    seen, out = set(), []
    for b in blocks:
        k = re.sub(r'[\W_]+', '', b.lower())
        # h4+ headings like "#### Image Unavailable" are UI; an h1-h3 named "Videos" is a real section
        if len(k) < 2 or k in seen or (not re.match(r'#{1,3} ', b) and UI_TEXT.match(re.sub(r'^#+ ', '', b))): continue
        seen.add(k); out.append(b)
    return out


def _convert_components(root, url, meta, ld, cands, judge, links, debug):
    from . import compose
    segs = compose.segments(root, url)
    ptype, how = compose.page_type(meta, ld, segs, cands, judge)
    compose.label(segs, ptype, meta, judge)
    body, dropped = compose.render(segs, ptype, meta, ld, cands)
    if debug is not None:
        debug.update(page_type=ptype, page_type_how=how, segments=segs, dropped=dropped)
    out = ['---'] + [f'{k}: {v}' for k, v in compact_meta(meta).items()] + [f'page_type: {ptype}'] + ld_lines(ld, meta) + ['---']
    body = dedupe(body)
    if links:
        kept = {id(s) for s in segs if compose.BY_NAME.get(s.label) is None or compose.BY_NAME[s.label].shape != 'drop'}
        seen, L = set(), []
        for s in segs:
            if id(s) not in kept: continue
            for t, u in s.links:
                if u not in seen and u.rstrip('/') != url.rstrip('/'):
                    seen.add(u); L.append(f'- [{ws(t)[:60]}]({u})')
        if L: body.append('## Links\n' + '\n'.join(L[:25]))
    return '\n'.join(out) + '\n\n' + '\n\n'.join(body) + '\n'


def compact_meta(meta):
    """Drop a description that only repeats the title."""
    m = dict(meta)
    key = lambda s: re.sub(r'[\W_]+', '', s.lower())
    if 'description' in m and 'title' in m and (key(m['description']) in key(m['title']) or key(m['title']) in key(m['description'])):
        del m['description']
    return m


def ld_lines(ld, meta):
    """JSON-LD as one line per type; repeated types become a count plus a few names; values that only repeat
    the title or description are dropped."""
    key = lambda s: re.sub(r'[\W_]+', '', str(s).lower())
    known = {key(v) for k, v in meta.items() if k in ('title', 'description')}
    by_type = {}
    for o in ld:
        if o.get('@type'): by_type.setdefault(str(o['@type']), []).append(o)
    lines = []
    for typ, objs in by_type.items():
        flats = []
        for o in objs:
            flat = {k: ws(str(v)) for k, v in o.items() if not k.startswith('@') and isinstance(v, (str, int, float))
                    and not isinstance(v, bool) and not str(v).startswith('http') and len(str(v)) < 200 and key(v) not in known}
            if flat and not (len(flat) == 1 and 'name' in flat): flats.append(flat)
        if len(flats) >= 3:
            names = [f.get('name') or f.get('headline') or '' for f in flats]
            lines.append(f'{typ} ({len(flats)}): ' + '; '.join(n for n in names[:3] if n) + ('; …' if len(flats) > 3 else ''))
        else:
            lines += [f'{typ}: ' + '; '.join(f'{k}={v}' for k, v in list(f.items())[:8]) for f in flats]
    return lines


def replace_grid(root, cand):
    """Find the rendered listing grid that the top data table describes and swap it for a marker, so the table
    appears once, where the listings were. Requires the grid to hold most of the keys the page shows and to be
    mostly made of table values (so a big content area that happens to mention a few names is never replaced)."""
    keys = list(dict.fromkeys(r[0] for r in cand.rows if len(r[0]) >= 6))
    if len(keys) < 3: return None
    cells = {v for r in cand.rows for v in r if len(v) >= 3}
    def score(n):
        text = ws(n.text(separator=' '))
        return sum(1 for k in keys if k in text), text
    total, _ = score(root)
    if total < 3: return None
    best = None
    for n in root.css('div,ul,ol,section,table'):
        hits, text = score(n)
        if hits >= max(3, 0.8 * total) and (best is None or len(text) < len(best[1])):
            best = (n, text)
    if not best: return None
    n, text = best
    covered = sum(len(v) for v in cells if v in text)
    if covered < 0.25 * len(text): return None
    n.replace_with(DATA_MARK)
    return n


OUTSIDE_SKIP = 'nav,footer,aside,header,form,dialog,[role="dialog"],[role="navigation"],[role="banner"],[role="contentinfo"],[aria-hidden="true"]'


def outside_prose(t, root, md):
    """<main> rarely holds everything: pages put an intro, a second column or the story itself beside it. Bring in
    prose outside it (paragraphs of 60+ chars, headings over them) that isn't link-dense or in a chrome region."""
    skip = {n.mem_id for n in t.body.css(OUTSIDE_SKIP)}
    inside = {root.mem_id}
    seen = {re.sub(r'\W+', ' ', b.lower()) for b in md.blocks}
    def chrome(n):
        p = n
        while p is not None:
            if p.mem_id in skip: return True
            if p.mem_id in inside: return True
            p = p.parent
        return False
    for n in t.body.css('p,h2,h3'):
        text = ws(n.text(separator=' '))
        if len(text) < (60 if n.tag == 'p' else 15) or chrome(n): continue
        links = sum(len(ws(a.text(separator=' '))) for a in n.css('a'))
        if links > 0.3 * len(text): continue
        key = re.sub(r'\W+', ' ', text.lower())
        if key in seen: continue
        seen.add(key)
        md.blocks.append(('#' * int(n.tag[1]) + ' ' + text) if n.tag != 'p' else text)


def main_root(t):
    """<main> / role=main / <article> when it really holds the page: at least half of the body's text outside
    menus and footers. Many sites mark only a slice (php.net docs, news homepages) and the rest would be lost."""
    if t.body is None: return t.body
    def size(n):
        drop = sum(len(x.text(separator=' ')) for x in n.css('script,style,noscript,nav,footer,header'))
        return len(n.text(separator=' ')) - drop
    total = size(t.body)
    for sel in ['main', '[role="main"]', 'article']:
        n = t.css_first(sel)
        if n and len(n.text()) > 500 and size(n) >= 0.75 * total: return n
    return t.body


def convert(html, url, links=True, judge=None, meta_only=False, mode=None, debug=None):
    """judge: a jev.Judge, False to force the heuristic, or None to follow GIVEMEMD_JEV.
    mode: 'components' (or GIVEMEMD_COMPONENTS=1) segments the page and renders catalog components;
    debug: a dict that receives the segments, their labels and the page type (for the eval suite).
    meta_only: the page is a login wall / block page; keep only what its metadata and embedded data say."""
    t = LexborHTMLParser(html)
    unstream(t)
    meta = frontmatter(t, url)
    ld = jsonld(t)
    cands = datatables.select_rules(datatables.candidates(t))
    if judge is None and jev.enabled():
        judge = jev.Judge()
    md = MD(url)
    grid = None
    if not meta_only:
        root = main_root(t)
        components = (mode or os.environ.get('GIVEMEMD_COMPONENTS') and 'components') in ('components', 'components-light')
        before = len(ws(root.text(separator=' '))) if mode != 'portal' else 0
        prune(root, None if components else judge or None, meta.get('title', '') + ' ' + url,
              light=mode in ('components-light', 'portal'))
        grid = replace_grid(root, cands[0]) if cands else None
        if components:
            return _convert_components(root, url, meta, ld, cands, judge or None, links, debug)
        md.walk(root); md.flush()
        if root is not t.body:
            outside_prose(t, root, md)
        trim_headlines(md)
        kept = sum(len(b) for b in md.blocks) - md.headline_chars
        if mode is None and kept < 2000 and kept < 0.25 * before:
            # a portal / homepage: the link lists ARE the content, and link-density pruning removed nearly everything
            return convert(html, url, links=links, judge=judge, mode='portal', debug=debug)
    out = ['---'] + [f'{k}: {v}' for k, v in compact_meta(meta).items()]
    out += ld_lines(ld, meta)
    if meta_only:
        out.append('partial: the site showed a login wall or block page; only its metadata and embedded data are included')
    out.append('---')
    body = dedupe(md.blocks)
    tables = [datatables.render([c]) for c in cands]
    at = next((i for i, b in enumerate(body) if DATA_MARK in b), None)
    if grid and at is not None:        # the listing grid's rows, in the grid's place
        rest = body[at].replace(DATA_MARK, '').strip()
        body[at:at + 1] = ([rest] if rest else []) + tables[0]
        tables = tables[1:]
    else:
        body = [b.replace(DATA_MARK, '').strip() for b in body if b.replace(DATA_MARK, '').strip()]
    body += [b for blk in tables for b in blk]
    if links:
        seen, L = set(), []
        for s, u in md.links:
            if u not in seen and u.rstrip('/') != url.rstrip('/'):
                seen.add(u); L.append(f'- [{ws(s)[:60]}]({u})')
        if L: body.append('## Links\n' + '\n'.join(L[:25]))
    return '\n'.join(out) + '\n\n' + '\n\n'.join(body) + '\n'


if __name__ == '__main__':
    print(convert(open(sys.argv[1], encoding='utf-8', errors='ignore').read(), sys.argv[2]))
