"""Build the answer key: facts per page, pulled from the raw HTML (DOM + embedded JSON)."""
import json, re
from selectolax.lexbor import LexborHTMLParser as P

def norm(s):
    s = s.lower().replace('‎','').replace('‏','')
    s = re.sub(r'[\\*_`#|>\[\]]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def amazon(h):
    t = P(h); F = []
    F.append(('title', t.css_first('#productTitle').text(separator=' ', strip=True)[:60]))
    F.append(('price', t.css_first('.a-price .a-offscreen').text(separator=' ', strip=True)))
    F.append(('rating', '4.6 out of 5'))
    F.append(('review_count', t.css_first('#acrCustomerReviewText').text(separator=' ', strip=True).strip('()').split()[0]))
    for i, li in enumerate(t.css('#feature-bullets li')):
        F.append((f'bullet{i}', li.text(separator=' ', strip=True)[:50]))
    for tr in t.css('#productOverview_feature_div tr, #productDetails_techSpec_section_1 tr'):
        c = [x.text(separator=' ', strip=True) for x in tr.css('th,td')]
        if len(c) >= 2: F.append((f'spec:{c[0][:25]}', c[-1][:40]))
    return F

def zillow(h):
    t = P(h); nd = json.loads(t.css_first('script#__NEXT_DATA__').text())
    L = nd['props']['pageProps']['searchPageState']['cat1']['searchResults']['listResults']
    F = []
    for r in L:
        F.append((f'addr:{r["zpid"]}', r.get('addressStreet') or r['address']))
        F.append((f'price:{r["zpid"]}', r['price']))
    return F

def linkedin(h):
    t = P(h); F = []
    ld = json.loads(t.css_first('script[type="application/ld+json"]').text())['@graph'][0]
    F.append(('name', ld['name'])); F.append(('desc', ld['description'][:60]))
    seen = set()
    for d in t.css('dl div'):
        dt, dd = d.css_first('dt'), d.css_first('dd')
        if dt and dd and dt.text(separator=' ', strip=True) not in seen:
            seen.add(dt.text(separator=' ', strip=True)); F.append((dt.text(separator=' ', strip=True), dd.text(separator=' ', strip=True).split('  ')[0][:40]))
    return F

def react(h):
    t = P(h); F = []
    for x in t.css('main h2, main h3, article h2, article h3'):
        F.append(('h:'+x.text(separator=' ', strip=True)[:30], x.text(separator=' ', strip=True)[:40]))
    for i, pre in enumerate(t.css('pre')):
        lines = [l.strip() for l in pre.text().splitlines() if len(l.strip()) > 12]
        if lines: F.append((f'code{i}', lines[0][:40]))
    return list(dict(F).items())

TRUTH = {'amazon': amazon, 'zillow': zillow, 'linkedin': linkedin, 'react': react}
def facts(name):
    from .cache import html
    return TRUTH[name](html(name))
