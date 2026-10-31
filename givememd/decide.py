"""Decision points: is a fetched page real content, a bot wall, or an empty JS shell?

The heuristic decides every clear case. With GIVEMEMD_JEV=1, short unclear pages (no vendor marker, no
blocking status) go to TypeSafe's Jev decision model: 99.4% vs 95.2% accuracy on 166 hand-labeled pages.
"""
import functools, json, os, re, urllib.request
from selectolax.lexbor import LexborHTMLParser

OK, BLOCKED, NEEDS_JS = 'ok', 'blocked', 'needs_js'

CHALLENGE = re.compile('|'.join([
    r'awsWafCookieDomainList', r'gokuProps',                     # AWS WAF (amazon.com)
    r'captcha-delivery\.com', r"var dd=\{'rt'",                  # DataDome (nytimes)
    r'cf-chl-', r'challenge-platform', r'<title>Just a moment',  # Cloudflare
    r'px-captcha', r'_pxAppId',                                  # PerimeterX / HUMAN
    r'/errors/validateCaptcha', r'Robot Check',                  # Amazon captcha
    r'Click the button below to continue shopping',              # Amazon soft block
    r"You've been blocked by network security",                  # Reddit
    r'Please enable JS and disable any ad blocker',
    r'Access Denied</title>', r'<title>Attention Required',
]), re.I)
JS_SHELL = re.compile(r'enable javascript|javascript is (disabled|required)|you need to enable javascript', re.I)


def visible_text(html):
    t = LexborHTMLParser(html)
    for n in t.css('script,style,noscript,template,svg'):
        n.decompose()
    return re.sub(r'\s+', ' ', t.body.text(separator=' ') if t.body else '').strip()


LOGIN_FORM = re.compile(r'<input[^>]+type=["\']?password', re.I)
LOGIN_TEXT = re.compile(r'\b(log ?in|sign ?in|sign ?up|create an account)\b', re.I)
LOGIN_URL = re.compile(r'/(accounts/)?(login|signin|sign-in|authwall|checkpoint)\b', re.I)
SHORT = 3000   # below this much visible text, a vendor marker or blocking HTTP status means "blocked"


def heuristic_status(html, status=200):
    """-> (label, reason, confident). Not confident = short page with no vendor marker and no blocking status."""
    if not html:
        return BLOCKED, f'empty body (HTTP {status})', True
    head = html[:200_000]
    m = CHALLENGE.search(head)
    text = visible_text(html)
    if m and len(text) < SHORT:
        return BLOCKED, f'challenge page ({m.group(0)[:40]})', True
    if status in (401, 403, 429, 503) and len(text) < SHORT:
        return BLOCKED, f'HTTP {status}', True
    # a password field (in the HTML, or as a visible label when a renderer drops the type attribute) + a login prompt
    if len(text) < SHORT and (LOGIN_FORM.search(head) or re.search(r'\bpassword\b', text[:1500], re.I)) \
            and LOGIN_TEXT.search(text[:1500]):
        return BLOCKED, 'login wall', True
    if len(text) >= SHORT:
        return OK, f'{len(text)} chars of text', True
    if len(text) < 400:
        scripts = html.count('<script')
        # one analytics <script> on example.com is not an app shell; an empty body with a script is
        if JS_SHELL.search(text) or scripts >= 3 or (scripts >= 1 and len(text) < 100):
            return NEEDS_JS, f'{len(text)} chars of text, {scripts} scripts', False
        if len(text) < 100:
            return BLOCKED, f'only {len(text)} chars of text', False
    return OK, f'{len(text)} chars of text', False


def page_status(html, status=200):
    """-> (label, reason). Heuristic by default; with GIVEMEMD_JEV=1, Jev decides the pages the heuristic is unsure of
    (short, no known vendor marker, no blocking status). Fails open to the heuristic on any API error or timeout."""
    label, why, confident = heuristic_status(html, status)
    if confident or os.environ.get('GIVEMEMD_JEV') != '1':
        return label, why
    try:
        a = jev_ask(jev_state(html, status))
        return JEV_LABEL[a['choice']], f"jev {a['choice']} ({a.get('confidence', 0):.2f}); heuristic: {why}"
    except Exception as e:
        return label, f'{why} (jev unavailable: {type(e).__name__})'


# ---------- compact page state for a scoring model (TypeSafe Jev) ----------
JEV_URL = 'https://api.typesafe.ai/v1/systemone'


@functools.lru_cache(maxsize=256)
def page_signals(html):
    t = LexborHTMLParser(html or '<html></html>')
    title = t.css_first('title')
    sig = {
        'title': re.sub(r'\s+', ' ', title.text()).strip()[:200] if title else '',
        'scripts': len(t.css('script')),
        'password': bool(t.css_first('input[type=password]')),
        'iframes': len(t.css('iframe')),
        'meta_refresh': bool(t.css_first('meta[http-equiv=refresh], meta[http-equiv=Refresh]')),
    }
    for n in t.css('script,style,noscript,template,svg'):
        n.decompose()
    text = re.sub(r'\s+', ' ', t.body.text(separator=' ') if t.body else '').replace('​', '').strip()
    sig['text'] = text
    return sig


def jev_state(html, status=200, head=900, middle=500):
    """Title + a few HTML signals + a visible-text excerpt (start and middle of the page). ~300-700 tokens."""
    s = page_signals(html or '')
    text = s['text']
    if len(text) > head + middle:
        mid = len(text) // 2
        excerpt = text[:head] + ' … ' + text[mid:mid + middle]
    else:
        excerpt = text
    return (f"HTTP status: {status}\nTitle: {s['title'] or '(none)'}\n"
            f"Visible text: {len(text)} chars; script tags: {s['scripts']}; iframes: {s['iframes']}; "
            f"password field: {'yes' if s['password'] else 'no'}; meta refresh: {'yes' if s['meta_refresh'] else 'no'}\n"
            f"Visible text excerpt:\n{excerpt or '(empty)'}")


JEV_QUESTION = {
    'type': 'choice',
    'instructions': 'A scraper fetched a URL and got the page summarized below. What did it receive?',
    'criteria': {
        'content': "the site's real page content (article, product, listing, docs, profile, homepage, search form, tool), even if short, or with a cookie/sign-in/error banner alongside real content",
        'block_page': "a bot check, captcha, 'verify you are human', access denied, rate limit, security block, or a generic error page shown instead of the content",
        'login_wall': 'a sign-in page shown instead of the requested content',
        'js_shell': 'an empty application shell or loading screen whose content only appears after JavaScript runs'}}
JEV_LABEL = {'content': OK, 'block_page': BLOCKED, 'login_wall': BLOCKED, 'js_shell': NEEDS_JS}


def _jev_key():
    from .jev import _key
    k = _key()
    if not k:
        raise RuntimeError('no Jev key')
    return k


@functools.lru_cache(maxsize=1024)
def jev_ask(state):
    """One Jev choice question on the compact state -> answer dict {'choice', 'confidence', 'probabilities'}."""
    body = json.dumps({'model': 'jev-latest', 'state': state, 'questions': {'page': JEV_QUESTION}}).encode()
    req = urllib.request.Request(JEV_URL, data=body, method='POST', headers={
        'Authorization': f'Bearer {_jev_key()}', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=float(os.environ.get('GIVEMEMD_JEV_TIMEOUT', '3'))) as r:
        a = json.loads(r.read())['answers']['page']
    if a.get('choice') not in JEV_LABEL:
        raise ValueError(f"unexpected Jev answer {a.get('choice')!r}")
    return a
