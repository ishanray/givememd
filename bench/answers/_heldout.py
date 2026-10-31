"""Held-out pages (never used for tuning) and their answer keys, built from each page's raw HTML."""
import json

from selectolax.lexbor import LexborHTMLParser as P  # noqa: F401


def txt(n): return n.text(separator=' ', strip=True)
def ld(t, typ):
    for s in t.css('script[type="application/ld+json"]'):
        try: d = json.loads(s.text())
        except Exception: continue
        for o in (d if isinstance(d, list) else d.get('@graph', [d])):
            if isinstance(o, dict) and typ in str(o.get('@type')): return o
    return {}


def k_wikipedia(t):
    F = [('h:' + txt(h), txt(h)) for h in t.css('#mw-content-text h2, #mw-content-text h3')]
    F += [('ib:' + txt(r.css_first('th')), txt(r.css_first('td'))[:30]) for r in t.css('.infobox tr') if r.css_first('th') and r.css_first('td')]
    return F

def k_hn(t): return [(f's{i}', txt(a)) for i, a in enumerate(t.css('.titleline > a'))]

def k_github(t):
    F = [('h:' + txt(h), txt(h)) for h in t.css('article.markdown-body h1, article.markdown-body h2, article.markdown-body h3')]
    d = t.css_first('meta[name="description"]')
    return F + [('desc', d.attributes['content'][:50])] if d else F

def k_recipe(t):
    r = ld(t, 'Recipe')
    return [(f'ing{i}', x) for i, x in enumerate(r.get('recipeIngredient', []))] + [('name', r.get('name', ''))]

def k_imdb(t):
    m = ld(t, 'Movie')
    F = [('name', m.get('name', '')), ('rating', str(m.get('aggregateRating', {}).get('ratingValue', ''))), ('desc', m.get('description', '')[:50])]
    F += [('dir:' + d['name'], d['name']) for d in m.get('director', [])] + [('actor:' + a['name'], a['name']) for a in m.get('actor', [])]
    return F

def k_pydocs(t):
    F = [('h:' + txt(h), txt(h).rstrip('¶')) for h in t.css('section h2, section h3')]
    F += [(f'code{i}', [l for l in p.text().splitlines() if len(l.strip()) > 10][0].strip()[:40]) for i, p in enumerate(t.css('pre')) if any(len(l.strip()) > 10 for l in p.text().splitlines())]
    F += [('api:' + txt(d)[:30], txt(d).rstrip('¶')[:30]) for d in t.css('dl.py > dt')]
    return F

def k_mdn(t):
    F = [('h:' + txt(h), txt(h)) for h in t.css('main h2, main h3')]
    F += [(f'code{i}', [l for l in p.text().splitlines() if len(l.strip()) > 10][0].strip()[:40]) for i, p in enumerate(t.css('pre')) if any(len(l.strip()) > 10 for l in p.text().splitlines())]
    return F

PAGES = {
    'wikipedia': ('https://en.wikipedia.org/wiki/Markdown', k_wikipedia),
    'hn': ('https://news.ycombinator.com/', k_hn),
    'github': ('https://github.com/microsoft/markitdown', k_github),
    'recipe': ('https://www.allrecipes.com/recipe/10813/best-chocolate-chip-cookies/', k_recipe),
    'imdb': ('https://www.imdb.com/title/tt0111161/', k_imdb),
    'pydocs': ('https://docs.python.org/3/library/pathlib.html', k_pydocs),
    'mdn': ('https://developer.mozilla.org/en-US/docs/Web/API/Fetch_API/Using_Fetch', k_mdn),
}
