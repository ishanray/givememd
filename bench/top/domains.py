"""Build the benchmark's domain list: Tranco top sites (general traffic) merged with AI-cited domains.

    python bench/top/domains.py --tranco <top-1m.csv> --want 2000 --out <dir>

1. Tranco (list id in the output header) in rank order, minus infrastructure (CDNs, APIs, ad/analytics, DNS)
   and adult domains, by name rules.
2. A curated AI-cited seed: the domains published AI-citation rankings name (Peec AI, LLM Pulse, Everything-PR;
   only top-10s are public) plus the categories agents read most. Curated, so labeled separately.
3. Probe each candidate's homepage (http tier only, 1 request per site) and keep real websites: an HTML page
   with a title or visible text, or a bot wall (a wall is a real outcome to benchmark, not a reason to skip).
"""
import argparse, concurrent.futures as cf, csv, json, re, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

AI_SEED = {
    'published': 'youtube.com google.com reddit.com facebook.com instagram.com linkedin.com trustpilot.com elpais.com ocu.org nih.gov '
                 'wikipedia.org forbes.com g2.com yelp.com medium.com techradar.com boe.es microsoft.com europa.eu abc.es '
                 'elespanol.com lavanguardia.com itechguides.com',
    'reference': 'britannica.com imdb.com goodreads.com wikihow.com merriam-webster.com dictionary.com investopedia.com '
                 'healthline.com mayoclinic.org webmd.com cdc.gov who.int clevelandclinic.org nature.com sciencedirect.com '
                 'arxiv.org pubmed.ncbi.nlm.nih.gov ncbi.nlm.nih.gov statista.com',
    'developer': 'github.com stackoverflow.com developer.mozilla.org docs.python.org npmjs.com pypi.org readthedocs.io '
                 'learn.microsoft.com docs.aws.amazon.com cloud.google.com huggingface.co dev.to geeksforgeeks.org w3schools.com '
                 'react.dev nodejs.org kubernetes.io docker.com',
    'news': 'nytimes.com bbc.com bbc.co.uk reuters.com cnn.com theguardian.com bloomberg.com apnews.com wsj.com washingtonpost.com '
            'cnbc.com theverge.com techcrunch.com wired.com arstechnica.com businessinsider.com npr.org usatoday.com foxnews.com',
    'commerce': 'amazon.com ebay.com walmart.com etsy.com bestbuy.com target.com homedepot.com ikea.com nike.com apple.com '
                'costco.com wayfair.com aliexpress.com',
    'reviews_local': 'capterra.com tripadvisor.com booking.com airbnb.com expedia.com zillow.com redfin.com realtor.com '
                     'indeed.com glassdoor.com producthunt.com consumerreports.org rtings.com',
    'social_community': 'x.com twitter.com tiktok.com pinterest.com quora.com threads.com tumblr.com substack.com '
                        'news.ycombinator.com discord.com twitch.tv',
}

INFRA = re.compile(r'(^|\.)(cdn|static|assets|img|images|media|api|apis|edge|dns|ns\d|mail|smtp|mx|ads?|adservice|track|tracking|'
                   r'analytics|metrics|telemetry|pixel|beacon|sync|push|update|updates|ocsp|crl|pki|cert|time|ntp|login|auth|'
                   r'gateway|proxy|cache|storage|blob|s3|cloudfront|akamai\w*|fastly\w*|edgekey|edgesuite|akadns|'
                   r'googleapis|gstatic|googlevideo|googleusercontent|googlesyndication|doubleclick|googletagmanager|'
                   r'gvt\d|1e100|ggpht|ytimg|fbcdn|whatsapp|cdninstagram|tiktokcdn\w*|byteoversea|ibytedtos|'
                   r'msftncsi|msedge|windowsupdate|live|office365|azureedge|azurefd|trafficmanager|icloud|aaplimg|'
                   r'mzstatic|apple-dns|digicert|letsencrypt|sentry|newrelic|nr-data|hotjar|segment|amplitude|'
                   r'criteo|taboola|outbrain|adnxs|rubiconproject|pubmatic|openx|casalemedia|moatads|scorecardresearch|'
                   r'demdex|omtrdc|everesttech|adsrvr|bidswitch|crwdcntrl|rlcdn|amazon-adsystem|ezviz\d*|xiaomi|miui|'
                   r'tuya\w*|samsungcloud\w*|roku|netflix-?cdn|nflx\w*|steamcontent|steamserver|epicgames|'
                   r'cloudflare-dns|one\.one|quad9|opendns|in-addr|arpa|local|internal|corp)(\.|$)', re.I)
INFRA_SUFFIX = re.compile(r'\.(arpa|local|internal)$|(akamaiedge|akamaized|akamaihd|edgekey|cloudfront|amazonaws|azureedge|'
                          r'trafficmanager|fastly|cloudapp|appspot|herokudns|vercel-dns|awsdns-\d+)\.', re.I)
ADULT = re.compile(r'porn|xvideo|xnxx|xhamster|redtube|youporn|onlyfans|chaturbate|stripchat|bongacams|livejasmin|'
                   r'cam4|camsoda|spankbang|eporner|hentai|rule34|nsfw|sex|xxx|fapello|erome|brazzers|tube8|motherless', re.I)


def tranco(path, limit):
    with open(path) as f:
        for row in csv.reader(f):
            if int(row[0]) > limit: break
            yield int(row[0]), row[1].strip().lower()


def probe(domain):
    try:
        return _probe(domain)
    except Exception as e:
        return {'domain': domain, 'keep': False, 'why': f'probe error ({type(e).__name__})'}


def _probe(domain):
    from curl_cffi import requests
    from givememd.fetch import decode
    from givememd.decide import heuristic_status, page_signals
    for url in (f'https://{domain}/', f'https://www.{domain}/'):
        try:
            r = requests.get(url, impersonate='chrome', timeout=15, allow_redirects=True,
                             headers={'Accept-Language': 'en-US,en;q=0.9'})
        except Exception as e:
            err = f'{type(e).__name__}'; continue
        ctype = r.headers.get('content-type', '')
        text = decode(r.content, ctype)
        if 'html' not in ctype and not text.lstrip()[:200].lower().startswith(('<!doctype', '<html')):
            return {'domain': domain, 'keep': False, 'why': f'not html ({ctype[:30]})', 'status': r.status_code}
        label, why, _ = heuristic_status(text, r.status_code)
        sig = page_signals(text)
        if label != 'ok':
            return {'domain': domain, 'keep': True, 'why': f'wall: {why}', 'status': r.status_code, 'final': str(r.url), 'title': sig['title'][:80]}
        if sig['title'] or len(sig['text']) >= 300:
            return {'domain': domain, 'keep': True, 'why': 'ok', 'status': r.status_code, 'final': str(r.url),
                    'title': sig['title'][:80], 'chars': len(sig['text'])}
        return {'domain': domain, 'keep': False, 'why': 'no title or text', 'status': r.status_code}
    return {'domain': domain, 'keep': False, 'why': f'unreachable ({err})'}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tranco', required=True)
    ap.add_argument('--list-id', default='')
    ap.add_argument('--want', type=int, default=2000)
    ap.add_argument('--scan', type=int, default=4000, help='how deep into Tranco to look')
    ap.add_argument('--out', required=True)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    seed = {d: cat for cat, ds in AI_SEED.items() for d in ds.split()}
    cands, skipped = [], {'infra': 0, 'adult': 0}
    for rank, d in tranco(a.tranco, a.scan):
        if ADULT.search(d): skipped['adult'] += 1; continue
        if INFRA.search(d) or INFRA_SUFFIX.search(d): skipped['infra'] += 1; continue
        cands.append((rank, d))
    print(f'tranco top {a.scan}: {len(cands)} candidates after name filters {skipped}', flush=True)
    probes = {}
    todo = [d for _, d in cands] + [d for d in seed if d not in dict((d, 1) for _, d in cands)]
    t0 = time.time()
    with cf.ThreadPoolExecutor(48) as ex:
        for i, p in enumerate(ex.map(probe, todo)):
            probes[p['domain']] = p
            if i % 250 == 0: print(f'  probed {i}/{len(todo)} in {time.time() - t0:.0f}s', flush=True)
    kept_tranco = [(r, d) for r, d in cands if probes[d]['keep']][:a.want]
    rows = [{'domain': d, 'source': 'tranco', 'rank': r, **probes[d]} for r, d in kept_tranco]
    have = {d for _, d in kept_tranco}
    for d, cat in seed.items():
        if d in have:
            next(x for x in rows if x['domain'] == d)['ai_seed'] = cat
        elif probes[d]['keep']:
            rows.append({'domain': d, 'source': 'ai_seed', 'ai_seed': cat, **probes[d]})
    (out / 'domains.json').write_text(json.dumps({'tranco_list_id': a.list_id, 'scan': a.scan, 'name_filtered': skipped,
                                                  'domains': rows}, indent=1))
    (out / 'probes.json').write_text(json.dumps(probes, indent=1))
    drop = {}
    for p in probes.values():
        if not p['keep']: drop[p['why'].split(' (')[0]] = drop.get(p['why'].split(' (')[0], 0) + 1
    walls = sum(1 for r in rows if r['why'].startswith('wall'))
    print(f'kept {len(rows)} domains ({len(kept_tranco)} tranco, deepest rank {kept_tranco[-1][0] if kept_tranco else "-"}; '
          f'{len(rows) - len(kept_tranco)} ai-seed only); {walls} show a bot/login wall to plain http; dropped: {drop}')


if __name__ == '__main__':
    main()
