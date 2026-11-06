"""Answer keys built from the raw HTML (embedded JSON + DOM), written before scoring any extractor output.

Each fact is (key, value) where value is a string or a tuple of acceptable renderings.
Facts cover the page's main records (name + the fields a reader needs: price, rating, date, venue...)
plus, for detail pages, the key attributes.
"""
import json, os, re
from selectolax.lexbor import LexborHTMLParser as P

PAGES = {  # name -> URL the page was fetched from
    'zillow': 'https://www.zillow.com/homes/Austin,-TX_rb/',
    'redfin': 'https://www.redfin.com/city/30818/TX/Austin',
    'airbnb': 'https://www.airbnb.com/s/Austin--TX/homes',
    'walmart_search': 'https://www.walmart.com/search?q=coffee+maker',
    'nike': 'https://www.nike.com/w/mens-running-shoes-37v7jznik1zy7ok',
    'nike_pdp': 'https://www.nike.com/t/alphafly-4-mens-road-racing-shoes-EC33rkiZ/IU4686-002',
    'ikea': 'https://www.ikea.com/us/en/cat/bookcases-10382/',
    'ikea_pdp': 'https://www.ikea.com/us/en/p/billy-bookcase-white-20522046/',
    'eventbrite': 'https://www.eventbrite.com/d/tx--austin/events/',
    'recipe': 'https://www.bbcgoodfood.com/recipes/easy-chocolate-cake',
    'goodreads': 'https://www.goodreads.com/book/show/4671.The_Great_Gatsby',
}


def norm(s):
    s = str(s).lower().replace('‎', '').replace('‏', '').replace(' ', ' ').replace('\xa0', ' ')
    s = re.sub(r'[\\*_`#|>\[\],"/]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return re.sub(r'\( ', '(', re.sub(r' (?=[.,;:!?)%\'’])', '', s))   # 'it .' and 'it.' are the same fact


from .cache import html  # noqa: E402
def tree(name): return P(html(name))
def nd(t, sel='script#__NEXT_DATA__'): return json.loads(t.css_first(sel).text())


def lds(t):
    out = []
    for s in t.css('script[type="application/ld+json"]'):
        try: j = json.loads(s.text())
        except Exception: continue
        out += j if isinstance(j, list) else j.get('@graph', [j])
    return out


def find(o, k):
    if isinstance(o, dict):
        if k in o: return o[k]
        o = list(o.values())
    if isinstance(o, list):
        for v in o:
            r = find(v, k)
            if r is not None: return r


def money(x):
    """79 -> ('79', '79.00'); 740000 -> ('740,000', '740000'); 64.97 -> ('64.97',)"""
    f = float(str(x).replace(',', '').replace('$', ''))
    if f == int(f):
        i = int(f); return (f'{i:,}', str(i), f'{i}.00')
    return (f'{f:,.2f}', f'{f:.2f}')


def zillow():
    L = nd(tree('zillow'))['props']['pageProps']['searchPageState']['cat1']['searchResults']['listResults']
    F = []
    for r in L:
        F.append((f'addr:{r["zpid"]}', r.get('addressStreet') or r['address']))
        F.append((f'price:{r["zpid"]}', r['price']))
    return F


def redfin():
    F = []
    for o in lds(tree('redfin')):
        if o.get('@type') == 'Product':
            street = o['name'].split(',')[0]
            F.append((f'addr:{street}', street))
            F.append((f'price:{street}', money(o['offers']['price'])))
    return F


def airbnb():
    d = json.loads(tree('airbnb').css_first('script#data-deferred-state-0').text())
    recs, seen, F = (find(d, 'searchResults') or []) + (find(d, 'mapSearchResults') or []), set(), []
    for r in recs:
        name = r.get('subtitle') or r.get('title')
        if name in seen: continue
        seen.add(name)
        F.append((f'name:{name[:30]}', name[:45]))
        pl = r['structuredDisplayPrice']['primaryLine']
        price = pl.get('discountedPrice') or pl.get('price') or next((c.get('discountedPrice') or c.get('price') for c in pl.get('orderedComponents') or [] if c.get('discountedPrice') or c.get('price')), None)
        if price: F.append((f'price:{name[:30]}', price))
        if r.get('avgRatingLocalized') and r['avgRatingLocalized'][0].isdigit():
            F.append((f'rating:{name[:30]}', r['avgRatingLocalized'].split()[0]))
    return F


def walmart_search():
    st = nd(tree('walmart_search'))['props']['pageProps']['initialData']['searchResult']['itemStacks']
    F, seen = [], set()
    for s in st:
        if not (s.get('title') or '').startswith('Results for'): continue   # main results, not "trending" rails
        for i in s['items']:
            if i.get('__typename') != 'Product' or i['usItemId'] in seen: continue
            seen.add(i['usItemId'])
            F.append((f'name:{i["usItemId"]}', i['name'][:50]))
            if i.get('price'): F.append((f'price:{i["usItemId"]}', money(i['price'])))
            if i.get('numberOfReviews'): F.append((f'reviews:{i["usItemId"]}', (f'{i["numberOfReviews"]:,}', str(i['numberOfReviews']))))
    return F


def nike():
    pg = nd(tree('nike'))['props']['pageProps']['initialState']['Wall']['productGroupings']
    F = []
    for g in pg:
        if not g.get('products'): continue
        p = g['products'][0]
        F.append((f'name:{p["productCode"]}', p['copy']['title'].strip()))
        F.append((f'price:{p["productCode"]}', money(p['prices']['currentPrice'])))
    return F


def nike_pdp():
    d = nd(tree('nike_pdp'))['props']['pageProps']['selectedProduct']
    F = [('title', d['productInfo']['fullTitle'].replace('  ', ' ')), ('price', money(d['prices']['currentPrice'])),
         ('color', d['colorDescription']), ('style', d['styleColor']),
         ('desc', d['productInfo']['productDescription'][:50])]
    F += [(f'size:{s["localizedLabel"]}', s['localizedLabel']) for s in d['sizes']]
    return F


def ikea():
    g = [o for o in lds(tree('ikea')) if o.get('mainEntity')][0]['mainEntity']['itemListElement']
    F = []
    for li in g:
        it = li['item']
        F.append((f'name:{li["position"]}', it['name']))
        F.append((f'price:{li["position"]}', money(it['offers']['priceSpecification'][0]['price'])))
        if it.get('aggregateRating'): F.append((f'reviews:{li["position"]}', str(it['aggregateRating']['reviewCount'])))
    return F


def ikea_pdp():
    p = [o for o in lds(tree('ikea_pdp')) if o.get('@type') == 'Product'][0]
    F = [('name', p['name'][:20]), ('price', money(p['offers']['price'])), ('rating', p['aggregateRating']['ratingValue']),
         ('reviews', (p['aggregateRating']['reviewCount'], f"{int(p['aggregateRating']['reviewCount']):,}")),
         ('mpn', p['mpn']), ('material', p['material']), ('height', p['height'].replace('"', '').strip()),
         ('depth', p['depth'].replace('"', '').strip())]
    F += [(f'review:{r["name"]}', r['name']) for r in p['review'][:5]]
    return F


def eventbrite():
    el = [o for o in lds(tree('eventbrite')) if o.get('@type') == 'ItemList'][0]['itemListElement']
    F = []
    for li in el:
        e = li['item']
        F.append((f'name:{li["position"]}', e['name'][:50]))
        if e.get('location', {}).get('name'): F.append((f'venue:{li["position"]}', e['location']['name']))
        F.append((f'date:{li["position"]}', e['startDate'][:10]))
    return F


def recipe():
    t = tree('recipe'); pc = json.loads(t.css_first('script#__POST_CONTENT__').text())
    F = [('ing:' + i['ingredientText'], i['ingredientText']) for g in pc['ingredients'] for i in g['ingredients']]
    for k, s in enumerate(pc['methodSteps']):
        txt = P(s['content'][0]['data']['value']).text().strip()
        F.append((f'step{k}', txt[:40]))
    F += [(f'nut:{n["label"]}', f'{n["value"]}') for n in pc['nutritions'][:4]]
    r = [o for o in lds(t) if o.get('@type') == 'Recipe'][0]
    F += [('prep', ('PT35M', '35 mins')), ('cook', ('PT20M', '20 mins')), ('serves', str(r['recipeYield'])), ('ratings', '526')]
    return list(dict(F).items())


def goodreads():
    b = [o for o in lds(tree('goodreads')) if o.get('@type') == 'Book'][0]
    F = [('title', b['name']), ('author', b['author'][0]['name']), ('rating', str(b['aggregateRating']['ratingValue'])),
         ('ratings', ('6,176,808', '6176808')), ('reviews', ('140,945', '140945')), ('pages', '180'),
         ('published', ('April 10, 1925', '1925-04-10')), ('isbn', b['isbn'])]
    for g in ['Classics', 'Fiction', 'School', 'Historical Fiction', 'Romance', 'Literature', 'Novels']:
        F.append((f'genre:{g}', g))
    return F


TRUTH = {k: globals()[k] for k in PAGES}


def facts(name): return TRUTH[name]()


def recall(name, md):
    n = norm(md); F = facts(name); hit, miss = [], []
    for k, v in F:
        alts = v if isinstance(v, tuple) else (v,)
        (hit if any(norm(a) and norm(a) in n for a in alts) else miss).append(k)
    return len(hit) / len(F), hit, miss


if __name__ == '__main__':
    for p in PAGES:
        F = facts(p); print(p, len(F), F[:4])
