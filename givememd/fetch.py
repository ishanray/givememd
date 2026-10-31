"""Fetch ladder: cheapest tier first, escalate only when the page is blocked or an empty JS shell.

  cache -> http (Chrome TLS fingerprint, asks for text/markdown) -> lightpanda -> chromium

Run on a server, every tier uses the server's IP. Run via the CLI or MCP server,
every tier runs on the caller's machine and uses the caller's IP.
"""
import ipaddress, os, re, shutil, socket, subprocess, time
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from .decide import BLOCKED, LOGIN_TEXT, LOGIN_URL, OK, heuristic_status, page_status

UA = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
LIGHTPANDA = os.environ.get('GIVEMEMD_LIGHTPANDA') or shutil.which('lightpanda')
CACHE_TTL = 600
_cache = {}


class UnsafeURL(ValueError):
    pass


@dataclass
class Result:
    url: str
    body: str = ''
    content_type: str = 'text/html'
    tier: str = ''
    ok: bool = False
    trace: list = field(default_factory=list)
    partial: bool = False       # every tier hit a wall; body is the walled page, worth only its metadata


def normalize(target):
    target = target.strip().lstrip('/')
    if '://' not in target:
        target = 'https://' + target
    u = urlsplit(target)
    if u.scheme not in ('http', 'https') or not u.hostname:
        raise UnsafeURL(f'unsupported URL: {target}')
    return target


ALLOWED_PORTS = {int(p) for p in os.environ.get('GIVEMEMD_ALLOWED_PORTS', '80,443').split(',') if p.strip()}
MAX_BYTES = int(os.environ.get('GIVEMEMD_MAX_BYTES', 15_000_000))
MAX_REDIRECTS = 5


def resolve_public(host):
    """-> one public IP for host. Refuses if ANY address it resolves to is private/loopback/link-local (SSRF):
    givememd.com/192.168.1.1 must never read the caller's router or a cloud metadata endpoint."""
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        raise UnsafeURL(f'cannot resolve {host}') from e
    ips = []
    for info in infos:
        ip = ipaddress.ip_address(info[4][0].split('%')[0])
        if not ip.is_global or ip.is_multicast:
            raise UnsafeURL(f'{host} resolves to non-public address {ip}')
        ips.append(ip)
    return ips[0]


def check_public(url):
    u = urlsplit(url)
    port = u.port or (443 if u.scheme == 'https' else 80)
    if port not in ALLOWED_PORTS:
        raise UnsafeURL(f'port {port} not allowed (GIVEMEMD_ALLOWED_PORTS={sorted(ALLOWED_PORTS)})')
    return resolve_public(u.hostname)


CHARSET = re.compile(rb'''<meta[^>]+charset=["']?([\w-]+)''', re.I)


def decode(content, ctype=''):
    """Bytes -> text using the header charset, then <meta charset>, then UTF-8; never raises (Shift-JIS, GBK,
    windows-1251 and friends are common in the top sites)."""
    m = re.search(r'charset=([\w-]+)', ctype or '', re.I) or CHARSET.search(content[:4096])
    names = [m.group(1).decode() if isinstance(m.group(1), bytes) else m.group(1)] if m else []
    for name in names + ['utf-8']:
        try:
            return content.decode(name)
        except (LookupError, UnicodeDecodeError):
            continue
    return content.decode('utf-8', errors='replace')


def tier_http(url):
    """One request per hop, each pinned to the address we just checked (no DNS rebinding between check and
    connect), redirects followed by hand so every hop is checked, response size capped."""
    from urllib.parse import urljoin
    from curl_cffi import CurlOpt, requests
    cur = url
    for _ in range(MAX_REDIRECTS + 1):
        u = urlsplit(cur)
        ip = check_public(cur)
        port = u.port or (443 if u.scheme == 'https' else 80)
        pin = f'{u.hostname}:{port}:' + (f'[{ip}]' if ip.version == 6 else str(ip))
        r = requests.get(cur, impersonate='chrome', timeout=20, allow_redirects=False, headers={
            'Accept': 'text/markdown, text/html;q=0.9, application/xhtml+xml;q=0.9, */*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'},
            curl_options={CurlOpt.RESOLVE: [pin], CurlOpt.MAXFILESIZE_LARGE: MAX_BYTES})
        loc = r.headers.get('location')
        if r.status_code in (301, 302, 303, 307, 308) and loc:
            cur = normalize(urljoin(cur, loc)); continue
        ctype = r.headers.get('content-type', '')
        return r.status_code, decode(r.content[:MAX_BYTES], ctype), ctype, cur
    raise UnsafeURL(f'more than {MAX_REDIRECTS} redirects')


def tier_lightpanda(url):
    if not LIGHTPANDA:
        raise RuntimeError('lightpanda not installed')
    p = subprocess.run([LIGHTPANDA, 'fetch', '--dump', 'html', url], capture_output=True, text=True, timeout=30)
    return (200 if p.returncode == 0 else 599), p.stdout, 'text/html', url


def tier_chromium(url):
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        b = pw.chromium.launch(headless=True)
        try:
            page = b.new_page(user_agent=UA, locale='en-US')
            resp = page.goto(url, wait_until='domcontentloaded', timeout=30_000)
            status = resp.status if resp else 0
            # JS challenges (AWS WAF, Cloudflare) solve themselves and reload; give them time
            deadline = time.time() + 15
            while True:
                try:
                    page.wait_for_load_state('networkidle', timeout=5_000)
                except Exception:
                    pass
                html = page.content()
                if heuristic_status(html, 200)[0] == OK or time.time() > deadline:   # no Jev calls while polling
                    break
                status = 200
                page.wait_for_timeout(1_500)
            return status, html, 'text/html', page.url
        finally:
            b.close()


def is_markdown(body, ctype):
    """Sites that honor Accept: text/markdown (Cloudflare, react.dev) sometimes label it text/plain."""
    head = body.lstrip()[:500].lower()
    return bool(head) and ('markdown' in ctype or 'text/plain' in ctype) and not head.startswith(('<!doctype', '<html', '<?xml', '{', '['))


TIERS = [('http', tier_http), ('lightpanda', tier_lightpanda), ('chromium', tier_chromium)]


def metadata_chars(html):
    """How much a walled page still says about itself (title + description). Login walls on Facebook,
    Instagram and LinkedIn keep the name, follower count and bio in their meta tags."""
    from selectolax.lexbor import LexborHTMLParser
    t = LexborHTMLParser(html[:300_000])
    d = t.css_first('meta[name="description"], meta[property="og:description"]')
    desc = (d.attributes.get('content') or '') if d else ''
    if len(desc) < 40 or LOGIN_TEXT.search(desc[:80]):     # "Create an account or log in to Instagram" says nothing
        return 0
    return len(desc)


def fetch(target, tiers=None, use_cache=True):
    url = normalize(target)
    check_public(url)
    hit = _cache.get(url)
    if use_cache and hit and time.time() - hit[0] < CACHE_TTL:
        r = hit[1]
        return Result(r.url, r.body, r.content_type, r.tier + '+cache', True, r.trace)
    res = Result(url)
    walled = None                         # (metadata chars, tier, body, final url) of the best walled page
    for name, fn in TIERS:
        if tiers and name not in tiers:
            continue
        t0 = time.time()
        try:
            status, body, ctype, final = fn(url)
        except Exception as e:
            res.trace.append(f'{name}: error {type(e).__name__}: {str(e)[:80]}')
            continue
        if final != url:
            check_public(final)          # redirects must not land on private addresses either
        if status == 200 and is_markdown(body, ctype):
            label, why, ctype = OK, 'site served markdown', 'text/markdown'
        elif LOGIN_URL.search(urlsplit(final).path) and not LOGIN_URL.search(urlsplit(url).path):
            label, why = BLOCKED, 'redirected to login'
        else:
            label, why = page_status(body, status)
        res.trace.append(f'{name}: {label} ({why}) {time.time() - t0:.1f}s')
        if label == OK:
            res.url, res.body, res.content_type, res.tier, res.ok = final, body, ctype, name, True
            if use_cache:
                _cache[url] = (time.time(), res)
            return res
        m = metadata_chars(body) if body and not LOGIN_URL.search(urlsplit(final).path) else 0
        if m and (walled is None or m > walled[0]):
            walled = (m, name, body, final)
    if walled:
        _, name, res.body, res.url = walled
        res.tier, res.partial = name, True
    return res
