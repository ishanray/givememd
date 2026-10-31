"""Answer keys + main-content regions for every eval page, all built from cached raw HTML.

Tuning pages (amazon, zillow, linkedin, react): keys in _tuning.py.
Held-out (wikipedia, github, pydocs, mdn): keys in _heldout.py.
New held-out (guardian, ars, blog, allbirds, forum): keys below, written from raw HTML before any output was viewed.
"""
import json, re, sys
from pathlib import Path
from selectolax.lexbor import LexborHTMLParser as P

from . import _heldout as heldout, _tuning as tuning_truth
from .cache import html as raw

def norm(s):
    s = s.lower().replace('‎', '').replace('‏', '').replace('&amp;', '&')
    s = re.sub(r'[\\*_`#|>\[\]¶]', ' ', s)
    return re.sub(r'\s+', ' ', s).strip()

def txt(n): return n.text(separator=' ', strip=True)
def lds(t):
    for s in t.css('script[type="application/ld+json"]'):
        try: d = json.loads(s.text())
        except Exception: continue
        for o in (d if isinstance(d, list) else d.get('@graph', [d])):
            if isinstance(o, dict): yield o
def paras(nodes, n=50, minlen=30): return [txt(p)[:n] for p in nodes if len(txt(p)) >= minlen]

def k_guardian(t):
    F = [('headline', txt(t.css_first('h1'))[:60]), ('standfirst', txt(t.css_first('[data-gu-name=standfirst]'))[:50])]
    F += [(f'p{i}', s) for i, s in enumerate(paras(t.css('[data-gu-name=body] p')))]
    for o in lds(t):
        if o.get('@type') == 'NewsArticle':
            F += [('author:' + a['name'], a['name']) for a in o.get('author', []) if isinstance(a, dict) and a.get('name')]
    return F

def k_ars(t):
    F = [('headline', txt(t.css_first('h1'))[:60])]
    F += [(f'p{i}', s) for i, s in enumerate(paras(t.css('.post-content p')))]
    F += [('h:' + txt(h), txt(h)) for h in t.css('.post-content h2, .post-content h3')]
    F += [('author', 'Kyle Orland')]
    return F

def k_blog(t):
    F = [('title', txt(t.css_first('h1.post-title'))), ('subtitle', txt(t.css_first('h3.subtitle')))]
    F += [(f'p{i}', s) for i, s in enumerate(paras(t.css('.available-content p')))]
    F += [('h:' + txt(h), txt(h)) for h in t.css('.available-content h2, .available-content h3')]
    return F

def k_allbirds(t):
    pg = next(o for o in lds(t) if o.get('@type') == 'ProductGroup')
    F = [('name', pg['name']), ('price', '$' + str(pg['offers']['price'])), ('desc', pg['description'][:50])]
    for h in t.css('main h2'):   # feature callouts: BREATHABLE / LIGHTWEIGHT / ...
        body = [x for x in h.parent.text(separator='|', strip=True).split('|') if x and x != txt(h)]
        if txt(h).isupper() and body: F.append(('feat:' + txt(h), body[0][:50]))
    F += [('mat:TENCEL', 'Breathable TENCEL™ Lyocell (tree fiber)'), ('mat:SweetFoam', 'SweetFoam® cushioning'), ('mat:merino', 'Soft, Merino-wool'),
          ('fit', 'Gently hugs your foot with a just-right, barefoot feel'), ('best:Commuting', 'Commuting')]
    return F

def k_forum(t):
    F = [('title', txt(t.css_first('h1')))]
    for i, post in enumerate(t.css('.topic-body')):
        u = post.css_first('[itemprop=author] [itemprop=name]')
        if u: F.append((f'user:{txt(u)}', txt(u)))
        ps = [p for p in post.css('.post > p') if len(txt(p)) >= 20]
        if ps: F.append((f'post{i}', txt(ps[0])[:50]))
    return F

def k_awesome(t):   # link-list stress page: headings + every 10th list entry's link text
    a = t.css_first('article.markdown-body')
    F = [('h:' + txt(h), txt(h)) for h in a.css('h2, h3') if txt(h) != 'Contents']
    lis = [li for li in a.css('li') if li.css_first('a') and len(txt(li.css_first('a'))) >= 4]
    return F + [(f'li{i}', txt(li.css_first('a'))) for i, li in enumerate(lis) if i % 10 == 0]

def k_wikilist(t):
    c = t.css_first('#mw-content-text')
    lis = [li for li in c.css('div.div-col li') if li.css_first('a') and len(txt(li.css_first('a'))) >= 4]
    return [(f'li{i}', txt(li.css_first('a'))) for i, li in enumerate(lis) if i % 10 == 0] + [('h:See also', 'See also')]

NEW = {'guardian': k_guardian, 'ars': k_ars, 'blog': k_blog, 'allbirds': k_allbirds, 'forum': k_forum, 'awesome': k_awesome, 'wikilist': k_wikilist}
URLS = {'amazon': 'https://www.amazon.com/dp/B0D1XD1ZV3', 'zillow': 'https://www.zillow.com/homes/Austin,-TX_rb/',
        'linkedin': 'https://www.linkedin.com/company/anthropic', 'react': 'https://react.dev/reference/react/useState',
        **{k: v[0] for k, v in heldout.PAGES.items()},
        'guardian': 'https://www.theguardian.com/technology/2026/oct/18/wikipedia-human-history-ai-future-under-threat',
        'ars': 'https://arstechnica.com/ai/2026/10/doordash-says-outside-ai-agents-have-only-led-to-hundreds-of-orders-so-far/',
        'blog': 'https://www.oneusefulthing.org/p/agency-and-agents', 'allbirds': 'https://www.allbirds.com/products/mens-tree-runners',
        'forum': 'https://discuss.python.org/t/making-performance-work-easier-in-cpython/109711',
        'awesome': 'https://github.com/sindresorhus/awesome-nodejs', 'wikilist': 'https://en.wikipedia.org/wiki/List_of_programming_languages'}
TUNING, HELDOUT, FRESH = ['amazon', 'zillow', 'linkedin', 'react'], ['wikipedia', 'github', 'pydocs', 'mdn'], ['guardian', 'ars', 'blog', 'allbirds', 'forum']
STRESS = ['awesome', 'wikilist']   # link-list pages: where link-density pruning is most likely to destroy content

def facts(name):
    if name in TUNING: F = [(k, v) for k, v in tuning_truth.TRUTH[name](raw(name))]
    elif name in HELDOUT: F = [(k, v) for k, v in heldout.PAGES[name][1](P(raw(name)))]
    else:
        F = NEW[name](P(raw(name)))
        vis = norm(P(raw(name)).body.text(separator=' '))          # sanity: every new fact must be visible in the raw DOM
        F = [(k, v) for k, v in F if norm(v) in vis]
    return list(dict((k, v) for k, v in F if norm(v)).items())

# Main-content regions (selectors chosen from raw HTML, before outputs were viewed). Text outside them counts as boilerplate.
REGION = {
    'amazon': ('#centerCol, #prodDetails, #productDetails_feature_div, #aplus_feature_div, #aplus, #productDescription_feature_div, '
               '#reviewsMedley, #postPurchaseWhatsInTheBox_MP_feature_div, #customerReviews, #cm-cr-dp-review-list, #important-information, #desktop_buybox', ''),
    'zillow': ('#grid-search-results, h1', ''),
    'linkedin': ('section.core-rail', ''),
    'react': ('article', ''),
    'wikipedia': ('#mw-content-text .mw-parser-output, h1', '.navbox, .mw-editsection, .metadata'),
    'github': ('article.markdown-body, .BorderGrid-cell, [aria-labelledby="folders-and-files"], h1', ''),
    'pydocs': ('div.body', ''),
    'mdn': ('main h1, main .layout__body section.content-section', '.article-footer'),
    'guardian': ('h1, [data-gu-name=standfirst], [data-gu-name=body], [data-gu-name=meta], figcaption', ''),
    'ars': ('article header, .post-content', '.ad-wrapper'),
    'blog': ('.post-header, h1.post-title, h3.subtitle, .available-content', ''),
    'allbirds': ('main', '[class*=recommendations_carousel]'),
    'forum': ('h1, .topic-body', ''),
    'awesome': ('article.markdown-body', ''),
    'wikilist': ('#mw-content-text .mw-parser-output, h1', '.navbox, .mw-editsection, .metadata'),
}

def region_text(name):
    t = P(raw(name))
    for n in t.css('script,style,svg,template'): n.decompose()
    inc, exc = REGION[name]
    if exc:
        for n in t.css(exc): n.decompose()
    return norm(' '.join(n.text(separator=' ') for n in t.css(inc)))
