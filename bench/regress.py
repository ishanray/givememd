"""Offline regression check: answer-key recall and tokens on every cached benchmark page (no network).

    python bench/regress.py [path-to-a-givememd-checkout]     # defaults to this checkout

Prints one JSON line per page. Run it on two checkouts to compare a change.
"""
import json, re, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
checkout = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT
sys.path[:0] = [str(checkout), str(ROOT)]

import tiktoken  # noqa: E402
from bench.answers import PAGES, facts, norm_for  # noqa: E402
from bench.answers.cache import html  # noqa: E402
from givememd.extract import convert  # noqa: E402

enc = tiktoken.get_encoding('o200k_base')
UI_PROBE = re.compile(r'(?i)^(#+ |- )?(loading|image (un)?available|double tap|sign in to continue|skip to|show more|'
                      r'see more|read more|view all|advertisement|back to top|videos?|images|360° view|cookie)')

for name, url in PAGES.items():
    try:
        page = html(name)
    except FileNotFoundError as e:
        print(json.dumps({'page': name, 'error': str(e)})); continue
    nf = norm_for(name)
    alts = lambda v: [nf(str(x)) for x in (v if isinstance(v, (tuple, list)) else (v,)) if nf(str(x))]
    F = [(k, v) for k, v in facts(name) if alts(v)]
    md = convert(page, url, links=False)
    n = nf(md)
    hit = [k for k, v in F if any(a in n for a in alts(v))]
    lines = [l.strip() for l in md.split('---', 2)[-1].splitlines() if l.strip()]
    plain = [l for l in lines if not l.startswith(('|', '#', '```', '- ['))]
    print(json.dumps({'page': name, 'facts': len(F), 'recall': round(len(hit) / max(len(F), 1), 3),
                      'tokens': len(enc.encode(md)),
                      'fragment_ratio': round(sum(1 for l in plain if len(re.sub(r'^- ', '', l)) < 20) / max(len(plain), 1), 2),
                      'ui_lines': sum(1 for l in lines if UI_PROBE.search(l)),
                      'missed': [k for k, v in F if k not in hit][:6]}), flush=True)
