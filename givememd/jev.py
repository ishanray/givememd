"""Optional TypeSafe Jev judge for prune(): classifies candidate DOM blocks as content vs boilerplate.
(decide.py asks Jev whether a fetched page is real content; both share the key lookup below.)

Off by default. Enabled with GIVEMEMD_JEV=1 plus a key in GIVEMEMD_JEV_KEY / TYPESAFE_API_KEY
(or a path in GIVEMEMD_JEV_KEY_FILE / TYPESAFE_KEY_FILE).
Every failure (no key, network, 429 after retries, bad response) returns None and prune() falls back to the heuristic.
"""
import hashlib, json, os, threading, time
from concurrent.futures import ThreadPoolExecutor

API = 'https://api.typesafe.ai/v1/systemone'
CATS = {
    'main_content': 'the body the page exists for: article text, product details, documentation, posts',
    'supporting_content': 'author-written supplements to the main content: see-also lists, references, further reading, specs, captions, bylines',
    'navigation': 'site menus, breadcrumbs, tables of contents, sidebars, pagination, language or category lists',
    'recommendations': "promos for other items: customers also bought, more stories, you may also like, trending, sponsored",
    'ads_promo': 'ads, upsells, signup or newsletter or app prompts, cookie banners, widgets, share buttons',
    'legal_footer': 'copyright, terms, privacy, corporate footer links',
}
KEEP = ('main_content', 'supporting_content')
INSTR = ('Classify this block of the web page described in the state. If the block mixes facts about the page subject '
         '(a price, rating, spec, paragraph of the article) with promotional text, it is main_content. Block:\n')
MAX_REQ_TOKENS = 40000          # API limit is 64k; stay well under
Q_OVERHEAD = 220                # measured: category list + per-question framing


def _key():
    k = os.environ.get('GIVEMEMD_JEV_KEY') or os.environ.get('TYPESAFE_API_KEY')
    path = os.environ.get('GIVEMEMD_JEV_KEY_FILE') or os.environ.get('TYPESAFE_KEY_FILE')
    if not k and path:
        try: k = open(path).read().strip()
        except OSError: k = None
    return k or None


def enabled():
    return os.environ.get('GIVEMEMD_JEV') == '1' and _key() is not None


class Judge:
    def __init__(self, key=None, timeout=4.0, per_request=None, cache_dir=None, post=None):
        self.key = key or _key()
        self.timeout, self.per_request = timeout, per_request      # per_request=1 -> one question per HTTP call
        self.cache_dir = cache_dir or os.environ.get('GIVEMEMD_JEV_CACHE')
        self._post = post                                           # injectable for tests
        self.stats = dict(requests=0, cached=0, questions=0, input_tokens=0, output_tokens=0, seconds=0.0, errors=0)
        self._lock = threading.Lock()

    def _send(self, body):
        if self._post: return self._post(body)
        from curl_cffi import requests
        for attempt in range(3):
            r = requests.post(API, headers={'Authorization': 'Bearer ' + self.key}, json=body, timeout=self.timeout)
            if r.status_code == 429:
                time.sleep(1.5 * (attempt + 1)); continue
            r.raise_for_status()
            return r.json()
        raise RuntimeError('rate limited')

    def _request(self, state, qs):
        body = {'model': 'jev-latest', 'state': state, 'questions': qs}
        path = None
        if self.cache_dir:
            h = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:24]
            path = os.path.join(self.cache_dir, h + '.json')
            if os.path.exists(path):
                with self._lock: self.stats['cached'] += 1
                j = json.load(open(path))
                self._account(j, j.get('_seconds', 0.0))
                return j
        t = time.time()
        j = self._send(body)
        dt = time.time() - t
        self._account(j, dt)
        if path:
            os.makedirs(self.cache_dir, exist_ok=True)
            json.dump({**j, '_seconds': dt}, open(path, 'w'))
        return j

    def _account(self, j, dt):
        u = j.get('usage', {})
        with self._lock:
            self.stats['requests'] += 1
            self.stats['input_tokens'] += u.get('input_tokens', 0)
            self.stats['output_tokens'] += u.get('output_tokens', 0)
            self.stats['seconds'] += dt

    def classify(self, state, blocks):
        """blocks: list of description strings -> list of {category: probability} (or None on any failure)."""
        if not blocks or not self.key: return None
        qs = [{'type': 'choice', 'instructions': INSTR + b, 'criteria': CATS} for b in blocks]
        chunks, cur, size = [], [], len(state) // 3
        for i, q in enumerate(qs):
            est = len(q['instructions']) // 3 + Q_OVERHEAD
            if cur and (size + est > MAX_REQ_TOKENS or (self.per_request and len(cur) >= self.per_request)):
                chunks.append(cur); cur, size = [], len(state) // 3
            cur.append(i); size += est
        if cur: chunks.append(cur)
        out = [None] * len(qs)
        t0 = time.time()
        try:
            with ThreadPoolExecutor(min(8, len(chunks))) as ex:
                res = list(ex.map(lambda c: (c, self._request(state, {f'b{i}': qs[i] for i in c})), chunks))
            for c, j in res:
                for i in c:
                    out[i] = j['answers'][f'b{i}']['probabilities']
        except Exception:
            with self._lock: self.stats['errors'] += 1
            return None
        finally:
            self.stats['questions'] += len(qs)
            self.stats['wall'] = self.stats.get('wall', 0.0) + time.time() - t0
        return out


def _ask(self, state, questions, max_tokens=30000):
    """Any set of questions against one state -> {id: answer} (None on any failure). Questions are split into
    requests that stay under the context limit (criteria are billed per question) and sent in parallel."""
    if not questions or not self.key: return None
    est = lambda q: (len(q['instructions']) + len(str(q.get('criteria', '')))) // 3 + 60
    chunks, cur, size = [], {}, len(state) // 3
    for k, q in questions.items():
        if cur and size + est(q) > max_tokens:
            chunks.append(cur); cur, size = {}, len(state) // 3
        cur[k] = q; size += est(q)
    if cur: chunks.append(cur)
    t0 = time.time()
    try:
        with ThreadPoolExecutor(min(8, len(chunks))) as ex:
            res = list(ex.map(lambda c: self._request(state, c), chunks))
        out = {}
        for j in res: out.update(j['answers'])
        return out
    except Exception:
        with self._lock: self.stats['errors'] += 1
        return None
    finally:
        self.stats['questions'] += len(questions)
        self.stats['wall'] = self.stats.get('wall', 0.0) + time.time() - t0


Judge.ask = _ask


def keep_prob(p):
    return sum(p.get(k, 0.0) for k in KEEP)
