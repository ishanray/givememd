"""Score the top-sites crawl without hand labels.

    python bench/top/score.py --data <dir> [--rerun-ours] [--mode default|components-light] [--domains a,b]

Per URL and tool (ours, jina, defuddle):
  usable      real content: >= 200 chars of text and no bot-wall / login / error page in the first 1,500 chars
              (one check for every tool, applied to the markdown they returned)
  ref_recall  facts pulled from the raw HTML we fetched (title, description, h1-h3, <p> sentences, JSON-LD strings)
              found in the output; only when our fetch got the page
  con_recall  "consensus" facts: sentences found in at least two tools' outputs; a fact only one tool has doesn't count
  tokens      o200k tokens; junk: lines of interface text

Per URL, ours vs each competitor: usable beats unusable; then the higher mean recall wins if the gap is > 5 points;
otherwise fewer tokens wins if > 15% fewer; otherwise a tie.
--rerun-ours re-extracts our markdown from the saved raw HTML with the current code (fast; no network).
"""
import argparse, collections, gzip, json, re, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import tiktoken  # noqa: E402
from selectolax.lexbor import LexborHTMLParser  # noqa: E402

enc = tiktoken.get_encoding('o200k_base')
TOOLS = ['ours', 'jina', 'defuddle']
WALL = re.compile(r"(?i)just a moment|verify you are (a )?human|are you a robot|captcha|access denied|403 forbidden|"
                  r"you've been blocked|request blocked|enable javascript|javascript is (disabled|required)|"
                  r"please (log|sign) ?in|log in to continue|sign in to continue|create an account or log in|"
                  r"unusual traffic|too many requests|rate limit|attention required|security check|"
                  r"page (not found|isn.t available)|404 not found|error 40[34]|something went wrong")
UI = re.compile(r'(?i)^(#+ |- )?(loading|image (un)?available|double tap|skip to|show more|see more|read more|view all|'
                r'advertisement|back to top|cookie|accept all|sign in|log in|sign up|subscribe)\b')


def body(tool, md):
    """Strip each tool's wrapper so the same text checks apply to all."""
    if tool == 'jina' and 'Markdown Content:' in md:
        md = md.split('Markdown Content:', 1)[1]
    elif md.startswith('---'):
        parts = md.split('---', 2)
        md = parts[2] if len(parts) == 3 else md
    return md


def text_of(md):
    t = re.sub(r'!\[[^\]]*\]\([^)]*\)', ' ', md)                 # images
    t = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', t)                 # links -> their text
    t = re.sub(r'[#*_`>|]', ' ', t)
    return re.sub(r'\s+', ' ', t).strip()


def norm(s):
    return re.sub(r'\s+', ' ', re.sub(r'[^\w\s]', ' ', s.lower())).strip()


def usable(tool, md):
    t = text_of(body(tool, md))
    return len(t) >= 200 and not WALL.search(t[:1500])


def ref_facts(html):
    t = LexborHTMLParser(html)
    F = []
    if t.css_first('title'): F.append(t.css_first('title').text())
    d = t.css_first('meta[name="description"]')
    if d and d.attributes.get('content'): F.append(d.attributes['content'])
    for n in t.css('script[type="application/ld+json"]'):
        for v in re.findall(r'"(?:name|headline|description|price|ratingValue|author)"\s*:\s*"([^"]{6,200})"', n.text()):
            F.append(v)
    for n in t.css('script,style,noscript,template,svg,nav,footer'):
        n.decompose()
    F += [h.text(separator=' ') for h in t.css('h1,h2,h3')]
    for p in t.css('p')[:60]:
        for sent in re.split(r'(?<=[.!?])\s+', p.text(separator=' ')):
            if len(sent.strip()) >= 60: F.append(sent)
    out = []
    for f in F:
        n = norm(f)[:80]
        if len(n) >= 12 and n not in out: out.append(n)
    return out[:120]


def sentences(md):
    t = text_of(md)
    return {norm(s)[:80] for s in re.split(r'(?<=[.!?])\s+|\n', t) if len(s.strip()) >= 40}


def outcome(a, b):
    """ours (a) vs competitor (b): 'win' | 'tie' | 'loss' and why."""
    if a['usable'] != b['usable']:
        return ('win' if a['usable'] else 'loss'), 'usable'
    if not a['usable']:
        return 'tie', 'both unusable'
    ra = [x for x in (a.get('ref_recall'), a.get('con_recall')) if x is not None]
    rb = [x for x in (b.get('ref_recall'), b.get('con_recall')) if x is not None]
    if ra and rb:
        da, db = sum(ra) / len(ra), sum(rb) / len(rb)
        if abs(da - db) > 0.05:
            return ('win' if da > db else 'loss'), 'recall'
    if a['tokens'] < 0.85 * b['tokens']: return 'win', 'tokens'
    if b['tokens'] < 0.85 * a['tokens']: return 'loss', 'tokens'
    return 'tie', 'close'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--data', required=True)
    ap.add_argument('--rerun-ours', action='store_true')
    ap.add_argument('--mode', default='default')
    ap.add_argument('--domains', default='')
    ap.add_argument('--out', default='')
    ap.add_argument('--tools', default='ours,jina,defuddle', help='score only these (e.g. ours,defuddle while Jina is still running)')
    a = ap.parse_args()
    global TOOLS
    TOOLS = a.tools.split(',')
    data = Path(a.data)
    if a.rerun_ours:
        from givememd.extract import convert
    rows = [json.loads(l) for l in (data / 'urls.jsonl').read_text().splitlines()]
    if a.domains: rows = [r for r in rows if r['domain'] in a.domains.split(',')]
    results = []
    for r in rows:
        d = data / 'runs' / r['domain']
        for which, url in r['urls']:
            got = {}
            for tool in TOOLS:
                p = d / f'{which}__{tool}.json'
                if p.exists(): got[tool] = json.loads(p.read_text())
            if not all(t in got for t in TOOLS): continue        # competitors haven't reached this URL yet
            html = None
            hp = d / f'{which}__ours.html.gz'
            if hp.exists(): html = gzip.decompress(hp.read_bytes()).decode('utf-8', 'replace')
            if a.rerun_ours and html and not got['ours'].get('markdown_native'):
                got['ours']['md'] = convert(html, got['ours'].get('final', url), links=False, mode=None if a.mode == 'default' else a.mode)
            mds = {t: (got[t].get('md') or '') if (t != 'ours' or got[t].get('ok')) else '' for t in TOOLS}
            ref = ref_facts(html) if html else []
            sents = {t: sentences(body(t, mds[t])) if usable(t, mds[t]) else set() for t in TOOLS}
            count = collections.Counter(s for t in TOOLS for s in sents[t])
            consensus = {s for s, c in count.items() if c >= 2}
            per = {}
            for t in TOOLS:
                b = body(t, mds[t]); n = norm(text_of(b))
                per[t] = {'usable': usable(t, mds[t]), 'tokens': len(enc.encode(b)),
                          'ref_recall': round(sum(1 for f in ref if f in n) / len(ref), 3) if ref and usable(t, mds[t]) else (0.0 if ref else None),
                          'con_recall': round(len(sents[t] & consensus) / len(consensus), 3) if consensus else None,
                          'junk': sum(1 for l in b.splitlines() if UI.match(l.strip()))}
            res = {'domain': r['domain'], 'which': which, 'url': url, 'source': r['source'], 'ai_seed': r.get('ai_seed'),
                   'rank': r.get('rank'), 'ours_tier': got['ours'].get('tier'), 'ours_trace': got['ours'].get('trace', [])[-1:],
                   **{f'{t}_{k}': v for t in TOOLS for k, v in per[t].items()}}
            for c in TOOLS[1:]:
                res[f'vs_{c}'], res[f'vs_{c}_why'] = outcome(per['ours'], per[c])
            results.append(res)
    out = Path(a.out) if a.out else data / f'score_{a.mode}{"_rerun" if a.rerun_ours else ""}.jsonl'
    out.write_text('\n'.join(json.dumps(x) for x in results))
    report(results)


def report(R):
    if not R: print('no scored URLs yet'); return
    n = len(R)
    print(f'{n} URLs scored ({len({r["domain"] for r in R})} domains)')
    for t in TOOLS:
        u = [r for r in R if r[f'{t}_usable']]
        rr = [r[f'{t}_ref_recall'] for r in R if r[f'{t}_ref_recall'] is not None]
        cr = [r[f'{t}_con_recall'] for r in R if r[f'{t}_con_recall'] is not None]
        tok = sorted(r[f'{t}_tokens'] for r in u)
        print(f'  {t:9} usable {len(u) / n:6.1%}   ref recall {sum(rr) / max(len(rr), 1):5.1%}   consensus recall {sum(cr) / max(len(cr), 1):5.1%}'
              f'   median tokens (usable) {tok[len(tok) // 2] if tok else 0:6}   junk lines/page {sum(r[f"{t}_junk"] for r in R) / n:4.1f}')
    for c in TOOLS[1:]:
        o = collections.Counter(r[f'vs_{c}'] for r in R)
        why = collections.Counter(r[f'vs_{c}_why'] for r in R if r[f'vs_{c}'] == 'loss')
        print(f'  ours vs {c:9} win {o["win"] / n:5.1%}  tie {o["tie"] / n:5.1%}  loss {o["loss"] / n:5.1%}   losses by cause: {dict(why)}')
    c = 'jina' if 'jina' in TOOLS else TOOLS[1]
    for seg, f in (('tranco', lambda r: r['source'] == 'tranco'), ('ai-cited', lambda r: r.get('ai_seed')),
                   ('longtail', lambda r: r['source'] == 'longtail'), ('indie', lambda r: r['source'] == 'indie')):
        S = [r for r in R if f(r)]
        if S:
            o = collections.Counter(r[f'vs_{c}'] for r in S)
            print(f'  [{seg}: {len(S)} urls] vs {c} win {o["win"] / len(S):5.1%} tie {o["tie"] / len(S):5.1%} loss {o["loss"] / len(S):5.1%}')


if __name__ == '__main__':
    main()
