"""givememd eval suite.

    python eval/run.py                     # all variants, all pages
    python eval/run.py --variants default,components --pages amazon,guardian -v

Variants
  default          the current extractor
  components       component pipeline, rules only (no model)
  components+jev   component pipeline, Jev labels (needs TYPESAFE_KEY_FILE; answers cached in GIVEMEMD_JEV_CACHE)
  components-light+jev   same, but pruning only drops what is never content; labels decide the rest

Metrics (per page, then averaged)
  recall           facts from the answer keys found in the output (keys built from raw HTML; see bench/regress.py)
  tokens           output tokens (o200k)
  content_lost     gold content sections (eval/gold) whose text is missing from the output
  junk_leaked      gold junk sections (shape 'drop' in the catalog) whose text appears in the output
  fields           gold header fields (e.g. product_header.price) found in the output
  page_type        page category correct (component variants)
  labels           gold sections whose segment got exactly the gold component (component variants)
  labels_alt       same, also accepting the gold set's listed alternatives (180 sections have one)
  keep_drop        kept-vs-dropped agrees with gold (a section pruned before labeling counts as dropped)
  shape            rendered layout (header/kv/prose/...) agrees with gold's component layout
  category         same, but only the component's category has to match
  fragments / ui   share of tiny lines / interface-text lines (layout)
  jev_tokens       Jev input tokens per page, and wall time

Raw pages are not in the repo (they are other sites' content): build the cache with `python bench/fetch_pages.py`.
The gold snippets were labeled on 2026-10-30 versions of these pages; re-fetched pages may have changed.
"""
import argparse, json, os, re, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path[:0] = [str(ROOT)]

import tiktoken  # noqa: E402
from bench.answers import PAGES as URLS, SETS, facts, norm_for  # noqa: E402
from bench.answers.cache import DATA, html  # noqa: E402
from givememd import jev  # noqa: E402
from givememd.components import BY_NAME  # noqa: E402
from givememd.extract import convert  # noqa: E402

enc = tiktoken.get_encoding('o200k_base')
PAGE_LIST = [n for s in ('tuning', 'heldout', 'fresh', 'stress', 'data') for n in SETS[s] if n not in ('awesome', 'wikilist', 'walmart_search', 'redfin', 'ikea', 'nike')] + \
            ['awesome', 'wikilist', 'walmart_search', 'redfin', 'ikea', 'nike']
UI_PROBE = re.compile(r'(?i)^(#+ |- )?(loading|image (un)?available|double tap|sign in to continue|skip to|show more|'
                      r'see more|read more|view all|advertisement|back to top|videos?|images|360° view|cookie)')


def norm(s):
    s = str(s).lower().replace('\u200e', '').replace('\xa0', ' ').replace('&amp;', '&')
    s = re.sub(r'[\\*_`#|>\[\],"/·]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()


def load(name):
    """-> html, url, facts (list of (key, value-or-alternatives))."""
    return html(name), URLS[name], facts(name)


def alts(v):
    return [norm(x) for x in (v if isinstance(v, (tuple, list)) else (v,)) if norm(x)]


def layout(md):
    lines, code = [], False
    for l in md.split('---', 2)[-1].splitlines():
        if l.startswith('```'): code = not code; continue
        if l.strip() and not code: lines.append(l.strip())
    plain = [l for l in lines if not l.startswith(('|', '#', '- ['))]
    return {'fragments': round(sum(1 for l in plain if len(re.sub(r'^- ', '', l)) < 20) / max(len(plain), 1), 3),
            'ui': sum(1 for l in lines if UI_PROBE.search(l)), 'dup': len(lines) - len(set(lines))}


def score(name, variant, judge_cache):
    html, url, facts = load(name)
    gold_path = HERE / 'gold' / f'{name}.json'
    gold = json.loads(gold_path.read_text()) if gold_path.exists() else None
    judge = jev.Judge(timeout=20, cache_dir=judge_cache) if variant.endswith('+jev') else False
    dbg, t0 = {}, time.time()
    md = convert(html, url, links=False, judge=judge, debug=dbg,
                 mode=variant.split('+')[0] if variant.startswith('components') else 'default')
    wall = time.time() - t0
    n = norm(md)
    F = [(k, v) for k, v in facts if alts(v)]
    r = {'page': name, 'variant': variant, 'tokens': len(enc.encode(md)), 'wall': round(wall, 2),
         'recall': round(sum(1 for _, v in F if any(a in n for a in alts(v))) / max(len(F), 1), 3), **layout(md)}
    if judge:
        r['jev_tokens'] = judge.stats['input_tokens']; r['jev_requests'] = judge.stats['requests']
    if gold:
        secs = [s for s in gold['sections'] if s['component'] in BY_NAME]
        content = [s for s in secs if BY_NAME[s['component']].shape != 'drop']
        junk = [s for s in secs if BY_NAME[s['component']].shape == 'drop']
        r['content_lost'] = round(sum(1 for s in content if norm(s['text']) not in n) / max(len(content), 1), 3)
        r['junk_leaked'] = round(sum(1 for s in junk if norm(s['text']) in n) / max(len(junk), 1), 3)
        fields = gold.get('fields', {})
        r['fields'] = round(sum(1 for v in fields.values() if norm(v) in n) / max(len(fields), 1), 3) if fields else None
        r['missed_fields'] = [k for k, v in fields.items() if norm(v) not in n]
        if 'segments' in dbg:
            r['page_type'] = int(dbg['page_type'] == gold['page_type'])
            segs = [(norm(s.text), s.label) for s in dbg['segments']]
            hits = cat = lenient = decision = shape = 0; wrong = []
            for s in secs:
                lab = next((l for t, l in segs if norm(s['text']) in t), 'pruned')
                g = s['component']
                hits += lab == g
                lenient += lab == g or lab in s.get('alt', [])
                pshape = BY_NAME[lab].shape if lab in BY_NAME else 'drop'          # pruned = dropped
                decision += (pshape == 'drop') == (BY_NAME[g].shape == 'drop')
                shape += pshape == BY_NAME[g].shape or any(BY_NAME[x].shape == pshape for x in s.get('alt', []) if x in BY_NAME)
                cat += lab in BY_NAME and BY_NAME[lab].category == BY_NAME[g].category or (lab == 'pruned' and BY_NAME[g].shape == 'drop')
                if lab != g: wrong.append(f"{g}->{lab}")
            r['labels'] = round(hits / max(len(secs), 1), 3); r['category'] = round(cat / max(len(secs), 1), 3)
            r['labels_alt'] = round(lenient / max(len(secs), 1), 3)
            r['keep_drop'] = round(decision / max(len(secs), 1), 3); r['shape'] = round(shape / max(len(secs), 1), 3)
            r['wrong'] = wrong[:8]
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--variants', default='default,components,components+jev')
    ap.add_argument('--pages', default=','.join(PAGE_LIST))
    ap.add_argument('-v', action='store_true')
    a = ap.parse_args()
    cache = os.environ.get('GIVEMEMD_JEV_CACHE', str(DATA / 'jev-cache'))
    variants = a.variants.split(',')
    if any(v.endswith('+jev') for v in variants) and not jev._key():
        sys.exit('components+jev needs TYPESAFE_API_KEY or TYPESAFE_KEY_FILE')
    rows = [score(p, v, cache) for p in a.pages.split(',') for v in variants]
    out = HERE / 'results'; out.mkdir(exist_ok=True)
    (out / f'{time.strftime("%Y%m%d-%H%M%S")}.json').write_text(json.dumps(rows, indent=1))

    cols = ['recall', 'tokens', 'content_lost', 'junk_leaked', 'fields', 'page_type', 'keep_drop', 'shape', 'labels_alt', 'category', 'jev_tokens']
    fmt = lambda k, x: '-' if x is None else (f'{x:.0%}' if k in ('recall', 'content_lost', 'junk_leaked', 'fields', 'page_type', 'labels', 'labels_alt', 'category', 'fragments', 'keep_drop', 'shape') else f'{x:.0f}' if isinstance(x, (int, float)) else str(x))
    if a.v:
        print(f"{'page':15}{'variant':16}" + ''.join(f'{c[:9]:>10}' for c in cols))
        for r in rows:
            print(f"{r['page']:15}{r['variant']:16}" + ''.join(f'{fmt(c, r.get(c)):>10}' for c in cols))
            if r.get('wrong') and r['variant'].endswith('+jev'): print(' ' * 31 + 'wrong labels: ' + ', '.join(r['wrong']))
            if r.get('missed_fields'): print(' ' * 31 + 'missed fields: ' + ', '.join(r['missed_fields']))
    print(f"\n{'variant':16}{'pages':>6}" + ''.join(f'{c[:9]:>10}' for c in cols))
    for v in variants:
        rs = [r for r in rows if r['variant'] == v]
        avg = lambda c: (lambda xs: sum(xs) / len(xs) if xs else None)([r[c] for r in rs if r.get(c) is not None])
        print(f"{v:16}{len(rs):6}" + ''.join(f'{fmt(c, avg(c)):>10}' for c in cols))


if __name__ == '__main__':
    main()
