"""Crawl the benchmark: our ladder on each domain's homepage + one inner content page, then competitors on the same URLs.

    python bench/top/run.py ours  --data <dir>     # phase A: our fetch ladder; picks the inner URL; saves raw HTML
    python bench/top/run.py jina  --data <dir>     # phase B: r.jina.ai (no key, throttled to stay under 20 req/min)
    python bench/top/run.py defuddle --data <dir>  # phase B: defuddle.md (gentle rate)

Resumable: a URL whose result file exists is skipped. One request at a time per site.
"""
import argparse, concurrent.futures as cf, gzip, hashlib, json, re, sys, threading, time
from pathlib import Path
from urllib.parse import urljoin, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

SKIP_PATH = re.compile(r'(?i)/(login|log-in|signin|sign-in|signup|sign-up|register|account|my|cart|basket|checkout|privacy|terms|'
                       r'cookie|legal|help|support|contact|about|careers|jobs?|press|search|tags?|sitemap|feed|rss|app|apps|'
                       r'download|subscribe|newsletter|lang|locale|settings|auth|oauth|ads|advertis\w*|cdn-cgi)(/|$|\?)')
MEDIA = re.compile(r'(?i)\.(jpg|jpeg|png|gif|webp|svg|pdf|zip|mp4|mp3|css|js|xml|json|ico)(\?|$)|/(images?|photos?|videos?)/\d*$')


def key(url):
    return hashlib.sha1(url.encode()).hexdigest()[:16]


def pick_inner(html, base, domain):
    """Prefer a link on the homepage's own host; fall back to other subdomains of the site."""
    host = (urlsplit(base).hostname or '').lower()
    return _pick(html, base, host, exact=True) or _pick(html, base, domain, exact=False)


def _pick(html, base, domain, exact):
    """The most content-like same-site link on the homepage: deep path, a slug or an id, not account/legal/search."""
    from selectolax.lexbor import LexborHTMLParser
    best, seen = None, set()
    for a in LexborHTMLParser(html).css('a[href]'):
        u = urljoin(base, a.attributes.get('href') or '')
        p = urlsplit(u)
        host = (p.hostname or '').lower()
        if p.scheme not in ('http', 'https') or not (host == domain or (not exact and host.endswith('.' + domain))): continue
        if MEDIA.search(p.path) or SKIP_PATH.search(p.path) or u in seen: continue
        seen.add(u)
        segs = [s for s in p.path.split('/') if s]
        if not segs: continue
        slug = max(segs, key=len)
        score = len(segs) + 2 * (slug.count('-') >= 2) + 2 * bool(re.search(r'\d{3,}', p.path)) + min(len(slug), 60) / 30
        if len((a.text() or '').strip()) >= 15: score += 1           # link text that reads like a headline/product name
        if best is None or score > best[0]: best = (score, u.split('#')[0])
    return best[1] if best else None


def save(d, name, obj, html=None):
    d.mkdir(parents=True, exist_ok=True)
    (d / f'{name}.json').write_text(json.dumps(obj))
    if html is not None:
        (d / f'{name}.html.gz').write_bytes(gzip.compress(html.encode('utf-8', 'replace')))


CHROMIUM = threading.Semaphore(3)


def ours_one(url, out):
    import importlib
    F = importlib.import_module('givememd.fetch')
    from givememd.extract import convert
    t0 = time.time()
    res, trace = None, []
    try:
        F.check_public(F.normalize(url))
    except Exception as e:
        return {'url': url, 'ok': False, 'trace': [f'unsafe: {e}']}, None
    html = None
    for name, fn in F.TIERS:
        ctx = CHROMIUM if name == 'chromium' else None
        try:
            if ctx: ctx.acquire()
            status, body, ctype, final = fn(url)
        except Exception as e:
            trace.append(f'{name}: error {type(e).__name__}'); continue
        finally:
            if ctx: ctx.release()
        if status == 200 and F.is_markdown(body, ctype):
            label, why = 'ok', 'markdown'
        elif F.LOGIN_URL.search(urlsplit(final).path) and not F.LOGIN_URL.search(urlsplit(url).path):
            label, why = 'blocked', 'redirected to login'
        else:
            from givememd.decide import page_status
            label, why = page_status(body, status)
        trace.append(f'{name}: {label} ({why})')
        if label == 'ok':
            html = body
            try:
                md = body if 'markdown' in (ctype or '') or why == 'markdown' else convert(body, final, links=False)
            except Exception as e:                   # one bad page must not stop the crawl; score.py re-extracts later
                md = ''; trace.append(f'convert error: {type(e).__name__}')
            res = {'url': url, 'final': final, 'ok': True, 'tier': name, 'status': status, 'trace': trace,
                   'seconds': round(time.time() - t0, 1), 'md': md, 'markdown_native': why == 'markdown'}
            break
    if res is None:
        res = {'url': url, 'ok': False, 'trace': trace, 'seconds': round(time.time() - t0, 1)}
    return res, html


def phase_ours(data, workers):
    doms = json.loads((data / 'domains.json').read_text())['domains']
    runs = data / 'runs'
    urls_path = data / 'urls.jsonl'
    done = {json.loads(l)['domain'] for l in urls_path.read_text().splitlines()} if urls_path.exists() else set()
    lock = threading.Lock()

    def do(dom):
        d = dom['domain']
        if d in done: return
        if dom.get('pages'):                       # indie set: given article URLs, no homepage step
            urls = []
            for i, u in enumerate(dom['pages']):
                r, html = ours_one(u, runs / d)
                save(runs / d, f'page{i}__ours', r, html)
                urls.append((f'page{i}', u))
            with lock, open(urls_path, 'a') as f:
                f.write(json.dumps({'domain': d, 'urls': urls, 'source': dom['source'], 'via': dom.get('via')}) + '\n')
            return
        home = dom.get('final') or f'https://{d}/'
        r, html = ours_one(home, runs / d)
        save(runs / d, 'home__ours', r, html)
        inner = pick_inner(html, r.get('final', home), d) if html else None
        urls = [('home', home)]
        if inner:
            ri, hi = ours_one(inner, runs / d)
            save(runs / d, 'inner__ours', ri, hi)
            urls.append(('inner', inner))
        with lock, open(urls_path, 'a') as f:
            f.write(json.dumps({'domain': d, 'urls': urls, 'source': dom['source'], 'rank': dom.get('rank'),
                                'ai_seed': dom.get('ai_seed')}) + '\n')

    t0, n = time.time(), 0
    with cf.ThreadPoolExecutor(workers) as ex:
        for _ in ex.map(do, doms):
            n += 1
            if n % 50 == 0: print(f'ours: {n}/{len(doms)} domains, {time.time() - t0:.0f}s', flush=True)
    print(f'ours: done {n} domains in {time.time() - t0:.0f}s', flush=True)
    (data / 'ours.done').write_text(str(time.time()))


def phase_competitor(data, tool, rpm, workers):
    from curl_cffi import requests
    base = {'jina': 'https://r.jina.ai/', 'defuddle': 'https://defuddle.md/'}[tool]
    gap = 60.0 / rpm
    lock, last = threading.Lock(), [0.0]
    t0, n = time.time(), 0

    def do(job):
        d, which, u = job
        p = data / 'runs' / d / f'{which}__{tool}.json'
        if p.exists(): return
        with lock:                                   # global pacing: one request every `gap` seconds
            wait = last[0] + gap - time.time()
            if wait > 0: time.sleep(wait)
            last[0] = time.time()
        t = time.time()
        try:
            r = requests.get(base + u, timeout=90)
            out = {'url': u, 'status': r.status_code, 'md': r.text, 'seconds': round(time.time() - t, 1)}
            if r.status_code == 429:                 # rate limited: back off and leave it for the resume pass
                time.sleep(30); return
        except Exception as e:
            out = {'url': u, 'status': 0, 'md': '', 'error': type(e).__name__, 'seconds': round(time.time() - t, 1)}
        save(data / 'runs' / d, f'{which}__{tool}', out)

    while True:                                       # follow urls.jsonl while our crawl is still adding to it
        finished = (data / 'ours.done').exists()
        rows = [json.loads(l) for l in (data / 'urls.jsonl').read_text().splitlines()] if (data / 'urls.jsonl').exists() else []
        jobs = [(r['domain'], which, u) for r in rows for which, u in r['urls']
                if not (data / 'runs' / r['domain'] / f'{which}__{tool}.json').exists()]
        if not jobs and finished: break
        with cf.ThreadPoolExecutor(workers) as ex:
            for _ in ex.map(do, jobs):
                n += 1
                if n % 100 == 0: print(f'{tool}: {n} urls, {time.time() - t0:.0f}s', flush=True)
        if not jobs: time.sleep(30)
    print(f'{tool}: done {n} urls in {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('phase', choices=['ours', 'jina', 'defuddle'])
    ap.add_argument('--data', required=True)
    ap.add_argument('--workers', type=int, default=16)
    ap.add_argument('--rpm', type=float, default=18)
    a = ap.parse_args()
    data = Path(a.data)
    if a.phase == 'ours':
        phase_ours(data, a.workers)
    else:
        phase_competitor(data, a.phase, a.rpm, min(a.workers, 12))
