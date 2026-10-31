"""Indie / small-web pages: Marginalia search results + Kagi Small Web feeds (latest post).

    python bench/top/indie.py --out <dir> [--smallweb <smallweb.txt>]

Marginalia (public API key, CC-BY-NC-SA results; used only to choose test URLs): ~20 hobby/personal-web queries,
one page per domain. Kagi Small Web: random sample of the listed feeds, newest item's link.
Writes <out>/domains.json with a 'pages' list per domain (run.py fetches those directly).
"""
import argparse, concurrent.futures as cf, json, random, re, sys, time
from pathlib import Path
from urllib.parse import urlsplit

QUERIES = ['personal blog', 'homebrew computer', 'sourdough bread', 'tiling window manager', 'birdwatching notes',
           'retro computing', 'zine', 'ham radio antenna', 'woodworking jig', 'poetry', 'static site generator',
           'permaculture garden', 'fountain pen ink', 'astronomy observing log', 'knitting pattern', 'bike touring',
           'home lab server', 'film photography', 'board game review', 'mechanical keyboard', 'emacs config', 'tea tasting']


def host(u):
    h = (urlsplit(u).hostname or '').lower()
    return h[4:] if h.startswith('www.') else h


def marginalia(per_query=12):
    from curl_cffi import requests
    out = {}
    for q in QUERIES:
        for attempt in range(4):
            r = requests.get('https://api2.marginalia-search.com/search', params={'query': q, 'count': 40, 'dc': 1},
                             headers={'API-Key': 'public'}, timeout=30)
            if r.status_code == 200: break
            time.sleep(10 * (attempt + 1))
        if r.status_code != 200:
            print(f'marginalia {q!r}: HTTP {r.status_code}', flush=True); continue
        n = 0
        for it in r.json().get('results', []):
            u = it.get('url', '')
            if u.startswith('http') and host(u) not in out and urlsplit(u).path not in ('', '/'):
                out[host(u)] = {'page': u, 'via': f'marginalia:{q}'}; n += 1
            if n >= per_query: break
        print(f'marginalia {q!r}: +{n}', flush=True)
        time.sleep(3)
    return out


def smallweb(path, n, rng):
    from curl_cffi import requests
    feeds = [l.strip() for l in open(path) if l.strip().startswith('http')]
    rng.shuffle(feeds)
    out = {}

    def latest(feed):
        try:
            r = requests.get(feed, timeout=15)
            xml = r.text
        except Exception:
            return None
        m = re.search(r'<item\b.*?<link>\s*([^<\s]+)\s*</link>', xml, re.S) or \
            re.search(r'<entry\b.*?<link[^>]*?href="([^"]+)"', xml, re.S)
        return m.group(1).replace('&amp;', '&') if m else None

    with cf.ThreadPoolExecutor(24) as ex:
        for feed, link in zip(feeds[:n * 2], ex.map(latest, feeds[:n * 2])):
            if link and link.startswith('http') and host(link) not in out and urlsplit(link).path not in ('', '/'):
                out[host(link)] = {'page': link, 'via': 'kagi-smallweb'}
            if len(out) >= n: break
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', required=True)
    ap.add_argument('--smallweb')
    ap.add_argument('--n-smallweb', type=int, default=250)
    ap.add_argument('--no-marginalia', action='store_true', help="skip Marginalia (its public key is often rate limited)")
    a = ap.parse_args()
    rng = random.Random(20261030)
    pages = {} if a.no_marginalia else marginalia()
    print(f'marginalia: {len(pages)} sites', flush=True)
    if a.smallweb:
        sw = smallweb(a.smallweb, a.n_smallweb, rng)
        print(f'kagi smallweb: {len(sw)} sites', flush=True)
        for h, v in sw.items(): pages.setdefault(h, v)
    rows = [{'domain': h, 'source': 'indie', 'via': v['via'], 'pages': [v['page']]} for h, v in pages.items()]
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'domains.json').write_text(json.dumps({'domains': rows}, indent=1))
    print(f'indie: {len(rows)} sites')


if __name__ == '__main__':
    main()
