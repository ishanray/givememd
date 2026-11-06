from pathlib import Path

import pytest

from givememd import decide
from givememd.decide import BLOCKED, NEEDS_JS, OK, jev_state, page_status
from givememd import datatables
from givememd.extract import clean_url, convert
from givememd.fetch import UnsafeURL, check_public, normalize
from selectolax.lexbor import LexborHTMLParser

FX = Path(__file__).parent / 'fixtures'


# ---------- links ----------
def test_clean_url_strips_tracking():
    u = clean_url('/dp/B0D1XD1ZV3/ref=sr_1_1?pd_rd_w=abc&content-id=x&utm_source=y&keywords=airpods', 'https://www.amazon.com/')
    assert u == 'https://www.amazon.com/dp/B0D1XD1ZV3?keywords=airpods'


def test_clean_url_rejects_non_http():
    assert clean_url('javascript:void(0)', 'https://a.com') is None
    assert clean_url('mailto:x@a.com', 'https://a.com') is None


# ---------- extraction ----------
def test_collapsed_see_more_content_is_kept_but_modals_dropped():
    html = '''<main><div class="a-expander-content" style="display:none"><p>Battery lasts 30 hours with case</p></div>
              <div class="modal" style="display:none"><p>Sign in to continue</p></div><p>Main product text here</p></main>'''
    md = convert(html, 'https://x.com')
    assert 'Battery lasts 30 hours' in md
    assert 'Sign in to continue' not in md


def test_link_dense_navigation_is_pruned():
    nav = '<div>' + ''.join(f'<a href="/c{i}">Category {i}</a>' for i in range(10)) + '</div>'
    md = convert(f'<body>{nav}<article><p>{"Real content. " * 40}</p></article></body>', 'https://x.com')
    assert 'Real content' in md and 'Category 3' not in md


def test_repeated_blocks_are_deduped():
    md = convert('<main>' + '<p>Free shipping on orders over $35</p>' * 3 + '<p>' + 'body ' * 120 + '</p></main>', 'https://x.com')
    assert md.count('Free shipping') == 1


def test_key_value_tables_become_compact_lines():
    md = convert('<main><table><tr><th>Brand</th><td>Apple</td></tr><tr><th>Color</th><td>White</td></tr></table>'
                 + '<p>' + 'x ' * 300 + '</p></main>', 'https://x.com')
    assert '- Brand: Apple' in md and '|' not in md.split('---', 2)[2].split('## Links')[0]


def test_code_blocks_survive():
    md = convert('<main><pre>const [age, setAge] = useState(28);</pre><p>' + 'docs ' * 100 + '</p></main>', 'https://x.com')
    assert '```\nconst [age, setAge] = useState(28);\n```' in md


def test_embedded_listings_become_a_table():
    """Listing pages lazy-load their cards but ship every listing in embedded app state (__NEXT_DATA__)."""
    t = LexborHTMLParser((FX / 'ok_listings.html').read_text())
    top = datatables.select_rules(datatables.candidates(t))[0]
    cols = datatables.short_names(top.cols)
    assert len(top.recs) >= 30
    rows = '\n'.join(datatables.render([top]))
    assert '101 Maple Ave' in rows and '$449,000' in rows
    assert 'addressStreet' not in cols                     # repeats address
    assert not any(c.lower().endswith(('id', 'url')) for c in cols)


def test_variant_rows_collapse_and_hash_columns_drop():
    recs = [{'title': f'Shoe {i % 3}', 'subtitle': f'Type {i % 3}', 'price': 100 + i, 'color': f'Color {i}', 'cardKey': f'{i:064x}'}
            for i in range(12)]
    c = datatables.Cand('x', [datatables.flatten(r) for r in recs])
    top = datatables.select_rules([c])[0]
    assert len(top.recs) == 3                                    # one row per shoe, not per colorway
    assert 'cardKey' not in top.cols
    assert 'Color 0' in top.rows[0][top.cols.index('color')] and 'Color 3' in top.rows[0][top.cols.index('color')]


def test_distinct_items_sharing_a_generic_title_are_not_merged():
    recs = [{'title': 'Home in Austin', 'name': f'Cozy place {i}', 'price': 90 + i, 'rating': 4 + i / 10} for i in range(8)]
    top = datatables.select_rules([datatables.Cand('x', recs)])[0]
    assert len(top.recs) == 8


def test_instagram_style_login_page_is_blocked():
    html = ('<html><head><title>Instagram</title></head><body><p>See everyday moments from your close friends.</p>'
            '<h2>Log into Instagram</h2><form><input name="username"><input type="password" name="password"></form></body></html>')
    assert page_status(html, 200)[0] == BLOCKED


def test_generic_login_metadata_is_not_a_partial_result():
    from givememd.fetch import metadata_chars
    assert metadata_chars('<meta name="description" content="Create an account or log in to Instagram - Share what you\'re into.">') == 0
    assert metadata_chars('<meta name="description" content="104M Followers, 94 Following, 4,986 Posts - NASA (@nasa) on Instagram">') > 0


def test_login_wall_keeps_only_metadata():
    html = ('<html><head><title>NASA | Facebook</title><meta name="description" content="NASA. 28,737,070 followers · '
            'Explore the universe and discover our home."></head><body><div>Log in to continue</div><form><input type="password"></form></body></html>')
    md = convert(html, 'https://facebook.com/NASA', meta_only=True)
    assert '28,737,070 followers' in md and 'partial:' in md and 'Log in to continue' not in md


def test_card_of_tiny_lines_becomes_one_line():
    card = '<li><div>$449,000</div><ul><li>4 bds</li><li>3 ba</li><li>2,428 sqft</li></ul><div>8709 Blaze Dr</div></li>'
    md = convert(f'<main><ul>{card}</ul><p>{"filler text " * 60}</p></main>', 'https://x.com', links=False)
    assert '$449,000 · 4 bds · 3 ba · 2,428 sqft · 8709 Blaze Dr' in md


def test_rendered_grid_is_replaced_by_its_data_table_in_place():
    homes = [(f'{100 + i} Oak Street', f'${400 + i},000') for i in range(6)]
    grid = '<div class="grid">' + ''.join(f'<div><b>{p}</b><span>{a}</span><span>Loading...</span></div>' for a, p in homes) + '</div>'
    data = '{"listings": [' + ','.join(f'{{"address": "{a}", "price": "{p}", "beds": {i % 4 + 1}}}' for i, (a, p) in enumerate(homes)) + ']}'
    html = (f'<html><body><main><h1>Homes</h1>{grid}<p>{"About this market. " * 40}</p></main>'
            f'<script type="application/json">{data}</script></body></html>')
    md = convert(html, 'https://x.com', links=False)
    assert md.count('100 Oak Street') == 1                    # once, in the table, not again as a card
    assert md.index('## Data') < md.index('About this market')  # where the grid was
    assert 'Loading' not in md


def test_description_repeating_the_title_is_dropped():
    md = convert('<html><head><title>Big Shoe Store: Red Shoe</title><meta name="description" content="Big Shoe Store: Red Shoe">'
                 '</head><body><main><p>' + 'shoe ' * 120 + '</p></main></body></html>', 'https://x.com')
    assert 'description:' not in md.split('---')[1]


def test_non_utf8_pages_decode():
    from givememd.fetch import decode
    sjis = '<html><head><meta charset="shift_jis"><title>ニュース</title></head></html>'.encode('shift_jis')
    assert 'ニュース' in decode(sjis)
    assert 'Москва' in decode('<p>Москва</p>'.encode('cp1251'), 'text/html; charset=windows-1251')
    assert decode(b'\xff\xfe broken') is not None


def test_portal_page_keeps_its_link_lists():
    menus = ''.join(f'<ul>' + ''.join(f'<li><a href="/s{i}{j}">Story headline number {i}{j} about events</a></li>' for j in range(8)) + '</ul>'
                    for i in range(6))
    md = convert(f'<html><body><main>{menus}<p>Short intro.</p></main></body></html>', 'https://portal.example', links=False)
    assert 'Story headline number 37 about events' in md


def test_extremely_deep_nesting_does_not_crash():
    html = '<main>' + '<span>' * 3000 + 'deep text here' + '</span>' * 3000 + '<p>' + 'body ' * 100 + '</p></main>'
    assert 'deep text here' in convert(html, 'https://x.com', links=False)


def test_react_streamed_segments_are_moved_into_place():
    html = ('<html><body><main><h1>News</h1><template id="B:0"></template><p>Loading…</p>'
            '<div hidden id="S:0"><p>' + 'The streamed story text arrives late. ' * 10 + '</p></div>'
            '<script>$RC("B:0","S:0")</script></main></body></html>')
    md = convert(html, 'https://x.com', links=False)
    assert 'streamed story text arrives late' in md
    assert md.index('# News') < md.index('streamed story')


def test_form_status_messages_are_dropped_but_js_toggled_panels_kept():
    html = ('<main><div class="w-form-fail">Oops! Something went wrong while submitting the form.</div>'
            '<div class="d-none">Nutrition: kcal 523 fat 29 g</div><div class="hidden md:block">Desktop navigation summary text</div>'
            '<p>' + 'Real article text. ' * 30 + '</p></main>')
    md = convert(html, 'https://x.com', links=False)
    assert 'Something went wrong' not in md
    assert 'Desktop navigation summary text' in md and 'kcal 523' in md


def test_tiny_static_page_does_not_escalate(monkeypatch):
    import givememd
    import importlib; F = importlib.import_module('givememd.fetch')
    calls = []
    monkeypatch.setattr(givememd, 'fetch', lambda t, tiers=None, use_cache=True: (calls.append(tiers),
                        F.Result(t, '<html><body><h1>Example</h1><p>Small page.</p></body></html>', 'text/html', 'http', True))[1])
    givememd.read('https://x.com')
    assert calls == [None]                                    # no render attempt for a page that simply is small


def test_empty_extraction_escalates_to_rendering(monkeypatch):
    import givememd
    import importlib; F = importlib.import_module('givememd.fetch')
    shell = '<html><body><div id="app"></div><p>' + 'x' * 10 + '</p>' + '<script src="/app.js"></script>' * 3 + '</body></html>'
    rendered = '<html><body><main><p>' + 'Rendered article body text. ' * 20 + '</p></main></body></html>'
    calls = []
    def fake_fetch(target, tiers=None, use_cache=True):
        calls.append(tiers)
        if tiers is None:
            return F.Result(target, shell, 'text/html', 'http', True)
        return F.Result(target, rendered, 'text/html', tiers[0], True)
    monkeypatch.setattr(givememd, 'fetch', fake_fetch)
    md, r = givememd.read('https://x.com')
    assert 'Rendered article body text' in md and r.tier == 'lightpanda'
    assert calls[1] == ['lightpanda', 'chromium']


def test_link_dense_story_cards_keep_headlines_not_menu_labels():
    menu = '<ul>' + ''.join(f'<li><a href="/m{i}">Menu {i}</a></li>' for i in range(8)) + '</ul>'
    cards = '<div>' + ''.join(f'<a href="/s{i}">Council approves the new river bridge plan {i}</a>' for i in range(8)) + '</div>'
    md = convert(f'<main><p>{"Front page intro text. " * 30}</p>{menu}{cards}</main>', 'https://news.example', links=False)
    assert 'Council approves the new river bridge plan 3 · Council approves the new river bridge plan 4' in md
    assert 'Menu 3' not in md


def test_prose_outside_main_is_kept_but_sidebar_links_are_not():
    html = ('<body><nav><a href="/">Home</a></nav>'
            '<section><h2>Why this matters</h2><p>The study followed 4,000 patients across nine hospitals over a decade of care.</p></section>'
            '<main><p>' + 'Main article text continues here. ' * 40 + '</p></main>'
            '<aside><p>Sponsored: buy our premium plan today and save big on everything you need.</p></aside></body>')
    md = convert(html, 'https://x.com', links=False)
    assert 'followed 4,000 patients across nine hospitals' in md and '## Why this matters' in md
    assert 'Sponsored' not in md


def test_hidden_tab_panels_are_kept():
    html = ('<main><div role="tablist"><button>Overview</button><button>Specs</button></div>'
            '<div role="tabpanel"><p>' + 'Overview text for the product. ' * 20 + '</p></div>'
            '<div role="tabpanel" hidden><p>Battery: 30 hours with the charging case included.</p></div></main>')
    assert 'Battery: 30 hours' in convert(html, 'https://x.com', links=False)


def test_html_comments_add_no_space():
    md = convert('<main><p>' + 'Nutrition per serving: fat 29<!-- -->g, carbs 59<!-- -->g. ' * 12 + '</p></main>', 'https://x.com', links=False)
    assert 'fat 29g' in md and '29 g' not in md


def test_no_space_before_punctuation_after_inline_elements():
    md = convert('<main><h2>Title <em>here</em>!</h2><p>' + 'It was <em>already validated it</em>. See <a href="/r">the report</a>, and (<a href="/l">Linux</a>) and <a href="/v">Vercel</a>\'s team. <span>A</span><span>B</span>. ' * 12 + '</p><table><tr><th>Date</th><th>Event</th></tr><tr><td>Oct 7</td><td>accepted into <code>net.git</code>.</td></tr></table><ul><li><a href="/c"><code>fix</code> (<code>abc123</code>)</a></li></ul></main>', 'https://x.com', links=False)
    for s in ['validated it.', 'the report,', '(Linux)', "Vercel's", 'A B.', '## Title here!', 'net.git.', 'fix (abc123)']:
        assert s in md, s
    assert ' .' not in md and ' ,' not in md


def test_system_browser_prefers_env_then_installed(monkeypatch, tmp_path):
    import importlib; F = importlib.import_module('givememd.fetch')
    monkeypatch.setenv('GIVEMEMD_CHROME', '/opt/my/chrome')
    assert F.system_browser() == '/opt/my/chrome'
    monkeypatch.delenv('GIVEMEMD_CHROME')
    fake = tmp_path / 'chrome'; fake.write_text('')
    monkeypatch.setattr(F, 'SYSTEM_BROWSERS', [str(fake)])
    assert F.system_browser() == str(fake)


def test_browser_download_can_be_disabled(monkeypatch):
    import importlib; F = importlib.import_module('givememd.fetch')
    monkeypatch.setenv('GIVEMEMD_NO_BROWSER_DOWNLOAD', '1')
    with pytest.raises(RuntimeError):
        F.install_headless_shell()


# ---------- block detection ----------
@pytest.mark.parametrize('name', ['block_aws_waf.html', 'block_shop_interstitial.html',
                                  'block_datadome.html', 'block_network_security.html'])
def test_block_pages_are_detected(name):
    label, why = page_status((FX / name).read_text(), 200)
    assert label in (BLOCKED, NEEDS_JS), why


@pytest.mark.parametrize('name', ['ok_docs.html', 'ok_listings.html'])
def test_real_pages_pass(name):
    assert page_status((FX / name).read_text(), 200)[0] == OK


def test_tiny_static_page_is_fine():
    html = ('<html><body><h1>Example Domain</h1><p>This domain is for use in illustrative examples in documents. '
            'You may use this domain in literature without prior coordination.</p></body></html>')
    assert page_status(html, 200)[0] == OK


def test_empty_spa_shell_needs_js():
    html = '<html><body><div id="root"></div>' + '<script src="/a.js"></script>' * 4 + '</body></html>'
    assert page_status(html, 200)[0] == NEEDS_JS


def test_tiny_page_with_one_script_is_ok():
    """example.com-style pages ship one <script>; that alone must not make ~150 chars of real text a JS shell."""
    assert page_status((FX / 'ok_tiny_static.html').read_text(), 200)[0] == OK


# ---------- optional Jev hybrid (GIVEMEMD_JEV=1) ----------
SOFT_BLOCK = ('<html><head><title>Hold on</title></head><body><p>We noticed unusual activity from your network. '
              'Press and hold to prove you are a person. Reference 8f2a91c</p></body></html>')


@pytest.fixture
def jev(monkeypatch):
    calls = []

    def use(answer=None, error=None):
        def fake(state):
            calls.append(state)
            if error:
                raise error
            return {'choice': answer, 'confidence': 0.9}
        monkeypatch.setattr(decide, 'jev_ask', fake)
        monkeypatch.setenv('GIVEMEMD_JEV', '1')
        return calls
    return use


def test_jev_is_off_by_default(monkeypatch):
    monkeypatch.delenv('GIVEMEMD_JEV', raising=False)
    monkeypatch.setattr(decide, 'jev_ask', lambda s: pytest.fail('Jev called without GIVEMEMD_JEV=1'))
    assert page_status(SOFT_BLOCK, 200)[0] == OK          # the heuristic's known blind spot


def test_jev_decides_short_unlisted_pages(jev):
    calls = jev('block_page')
    label, why = page_status(SOFT_BLOCK, 200)
    assert label == BLOCKED and 'jev' in why and len(calls) == 1
    assert 'unusual activity' in calls[0] and len(calls[0]) < 2500


@pytest.mark.parametrize('answer,label', [('content', OK), ('login_wall', BLOCKED), ('js_shell', NEEDS_JS)])
def test_jev_choices_map_to_labels(jev, answer, label):
    jev(answer)
    assert page_status(SOFT_BLOCK, 200)[0] == label


@pytest.mark.parametrize('name,status', [('block_aws_waf.html', 200), ('block_datadome.html', 200),
                                         ('ok_docs.html', 200)])
def test_jev_not_called_when_heuristic_is_confident(jev, name, status):
    calls = jev('content')
    page_status((FX / name).read_text(), status)
    assert calls == []


def test_jev_not_called_on_blocking_status_or_empty_body(jev):
    calls = jev('content')
    assert page_status(SOFT_BLOCK, 403)[0] == BLOCKED
    assert page_status('', 202)[0] == BLOCKED
    assert calls == []


def test_jev_fails_open_to_heuristic(jev):
    import urllib.error
    jev(error=urllib.error.URLError('timeout'))
    label, why = page_status(SOFT_BLOCK, 200)
    assert label == OK and 'jev unavailable' in why


def test_jev_state_is_compact():
    st = jev_state((FX / 'ok_listings.html').read_text(), 200)
    assert len(st) < 2500 and st.startswith('HTTP status: 200')


# ---------- SSRF guard ----------
@pytest.mark.parametrize('target', ['http://127.0.0.1/', 'http://localhost:8080/admin', 'http://169.254.169.254/latest/meta-data/',
                                    'http://10.0.0.1/', 'http://192.168.1.1/', 'http://[::1]/', 'http://0.0.0.0/'])
def test_private_targets_refused(target):
    with pytest.raises(UnsafeURL):
        check_public(normalize(target))


@pytest.mark.parametrize('target', ['file:///etc/passwd', 'ftp://example.com/x', 'gopher://example.com'])
def test_non_http_refused(target):
    with pytest.raises(UnsafeURL):
        normalize(target)


def _fake_dns(monkeypatch, answers):
    import importlib, socket
    F = importlib.import_module('givememd.fetch')
    seq = iter(answers)
    monkeypatch.setattr(socket, 'getaddrinfo', lambda host, *a, **k: [(None, None, None, None, (next(seq), 0))])
    return F


def test_http_tier_pins_the_checked_address(monkeypatch):
    """DNS rebinding: the name resolves public at check time; the connection must still go to that address."""
    F = _fake_dns(monkeypatch, ['93.184.215.14', '127.0.0.1'])
    seen = {}

    class R:
        status_code, headers, content = 200, {'content-type': 'text/html'}, b'<p>ok</p>'

    import curl_cffi.requests as cr
    from curl_cffi import CurlOpt
    monkeypatch.setattr(cr, 'get', lambda url, **kw: (seen.update(kw), R)[1])
    F.tier_http('https://rebind.example/')
    assert seen['curl_options'][CurlOpt.RESOLVE] == ['rebind.example:443:93.184.215.14']
    assert seen['allow_redirects'] is False


def test_redirect_to_a_private_address_is_refused(monkeypatch):
    F = _fake_dns(monkeypatch, ['93.184.215.14', '169.254.169.254'])

    class R:
        status_code, headers, content = 302, {'location': 'http://metadata.internal/latest/'}, b''

    import curl_cffi.requests as cr
    monkeypatch.setattr(cr, 'get', lambda url, **kw: R)
    with pytest.raises(UnsafeURL):
        F.tier_http('https://redirector.example/')


def test_non_standard_ports_refused():
    with pytest.raises(UnsafeURL):
        check_public(normalize('http://example.com:6379/'))


def test_bare_domain_normalized():
    assert normalize('/amazon.com/dp/B0D1XD1ZV3') == 'https://amazon.com/dp/B0D1XD1ZV3'
