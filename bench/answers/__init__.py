"""Answer keys for the benchmark pages: facts a good conversion must contain, built from each page's raw HTML.

    from bench.answers import PAGES, facts, norm_for
    facts('amazon')      -> [(key, value-or-tuple-of-accepted-spellings), ...]

Sets: tuning (pages the extractor was developed on), heldout / fresh (never tuned on), stress (link-list pages),
data (pages whose content lives in embedded JSON).
"""
from . import _data, _fresh

SETS = {
    'tuning': ['amazon', 'zillow', 'linkedin', 'react'],
    'heldout': ['wikipedia', 'github', 'pydocs', 'mdn'],
    'fresh': ['guardian', 'ars', 'blog', 'allbirds', 'forum'],
    'stress': ['awesome', 'wikilist'],
    'data': [p for p in _data.PAGES if p != 'zillow'],
}
_ALL = {**_fresh.URLS, **_data.PAGES}
PAGES = {n: _ALL[n] for names in SETS.values() for n in names}     # name -> URL


def set_of(name):
    return next(s for s, names in SETS.items() if name in names)


def facts(name):
    return _data.facts(name) if set_of(name) == 'data' else _fresh.facts(name)


def norm_for(name):
    return _data.norm if set_of(name) == 'data' else _fresh.norm
