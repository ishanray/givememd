"""Component pipeline: segmentation, labeling rules, Jev labels via a fake judge, header filling, rendering."""
from selectolax.lexbor import LexborHTMLParser

from givememd import compose
from givememd.components import BY_CATEGORY, BY_NAME, CATALOG, CATEGORIES
from givememd.extract import convert

PRODUCT = '''<html><head><title>Acme Headphones</title></head><body><main>
<div id="title"><h1>Acme Noise Cancelling Headphones</h1></div>
<div id="rating"><span>4.6 out of 5 stars</span> <span>(1,234)</span></div>
<div id="buy"><div><span>$99.00</span></div><div><p>Get a $50 gift card instantly upon approval for the Acme Card. No annual fee.</p></div></div>
<div id="ui"><span>Image Unavailable</span></div>
<table><tr><th>Brand</th><td>Acme</td></tr><tr><th>Color</th><td>Black</td></tr><tr><th>Weight</th><td>250 g</td></tr></table>
<div id="desc"><p>''' + 'These headphones block noise on planes and trains and last thirty hours on a charge. ' * 5 + '''</p></div>
</main></body></html>'''


class FakeJudge:
    """Answers like Jev would, from a {substring: (component, confidence)} table."""
    def __init__(self, table, page='commerce'):
        self.table, self.page, self.calls = table, page, []

    def ask(self, state, qs):
        self.calls.append(qs)
        out = {}
        for k, q in qs.items():
            if k == 'page':
                out[k] = {'choice': self.page, 'confidence': 0.9}; continue
            hit = next(((c, p) for sub, (c, p) in self.table.items() if sub in q['instructions']), ('article_body', 0.5))
            assert hit[0] in q['criteria'], f'{hit[0]} not offered'
            out[k] = {'choice': hit[0], 'confidence': hit[1]}
        return out


def segs_of(html):
    t = LexborHTMLParser(html)
    return compose.segments(t.css_first('main'), 'https://x.com')


def test_catalog_is_consistent():
    assert len(CATALOG) >= 100
    assert set(c.category for c in CATALOG) == set(CATEGORIES)
    assert all(len(v) <= 255 for v in BY_CATEGORY.values())
    for c in CATALOG:
        assert c.shape in {'header', 'kv', 'bullets', 'prose', 'steps', 'qa', 'table', 'cards', 'code', 'links', 'drop'}, c.name


def test_price_is_split_from_the_promo_next_to_it():
    texts = [s.text for s in segs_of(PRODUCT)]
    assert '$99.00' in texts
    assert not any('$99.00' in t and 'gift card' in t for t in texts)


def test_heading_attaches_to_the_section_after_it():
    segs = segs_of('<main><h2>Specs</h2><p>' + 'Battery lasts long. ' * 10 + '</p></main>')
    assert len(segs) == 1 and segs[0].blocks[0] == '## Specs'


def test_stacked_empty_headings_collapse():
    html = '<main>' + ''.join(f'<h3>step {i}</h3>' for i in range(1, 8)) + '<div><p>' + 'Mix the flour. ' * 20 + '</p></div></main>'
    md = convert(html, 'https://x.com', mode='components', judge=False, links=False)
    assert md.count('### step') == 1


def test_rules_label_without_a_model():
    md = convert(PRODUCT, 'https://x.com', mode='components', judge=False, links=False)
    assert 'Image Unavailable' not in md                    # ui_chrome rule
    assert '- Brand: Acme' in md                            # key/value rule
    assert 'thirty hours' in md                             # long prose kept


def test_jev_labels_fill_the_header_and_drop_the_promo():
    judge = FakeJudge({'Acme Noise': ('product_header', 0.95), 'out of 5': ('review_summary', 0.9),
                       '$99.00': ('price_offer', 0.95), 'gift card': ('promo_ad', 0.97)})
    md = convert(PRODUCT, 'https://x.com', mode='components', judge=judge, links=False)
    assert '# Acme Noise Cancelling Headphones' in md
    head = md[:md.index('## Specs')]                        # price and rating sit in the header, above the sections
    assert '**Price:** $99.00' in head and '4.6 out of 5 stars (1,234)' in head
    assert 'gift card' not in md
    assert 'page_type: commerce' in md


def test_unsure_junk_label_keeps_the_content():
    judge = FakeJudge({'gift card': ('promo_ad', 0.55)})
    md = convert(PRODUCT, 'https://x.com', mode='components', judge=judge, links=False)
    assert 'gift card' in md


def test_most_specific_jsonld_entity_wins():
    ld = [{'@type': 'VideoObject', 'name': 'How to bake'}, {'@type': 'Recipe', 'name': 'Easy chocolate cake', 'totalTime': 'PT55M'}]
    comp, vals = compose.ld_header(ld, 'food_health')
    assert comp.name == 'recipe' and vals['name'] == 'Easy chocolate cake'
    assert compose.page_type({}, ld, [], [], None)[0] == 'food_health'


def test_options_offered_to_the_model_are_bounded():
    for cat in CATEGORIES:
        if cat == 'chrome': continue
        opts = compose.options(cat)
        assert len(opts) <= 45 and all(n in BY_NAME for n in opts)


def test_steps_keep_order_and_lose_bare_step_headings():
    seg = compose.Segment(['## Method', '### step 1', 'Heat the oven.', '### step 2', 'Mix the flour.'], 'ul')
    out = compose.render_segment(seg, BY_NAME['instructions'], None)
    assert out == ['## Method', '1. Heat the oven.', '2. Mix the flour.']


def test_interior_headings_stay_in_place():
    seg = compose.Segment(['## Guide', 'Intro text here.', '### Part A', 'Body of part A.'], 'div')
    out = compose.render_segment(seg, BY_NAME['article_body'], None)
    assert out == ['## Guide', 'Intro text here.', '### Part A', 'Body of part A.']
