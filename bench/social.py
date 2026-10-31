"""givememd vs r.jina.ai (free, no key) on social and hard-to-read pages.

Checks were written per page BEFORE looking at either tool's output: regexes for the facts a reader
of that page needs (follower counts, captions, titles, view counts). A check passes if it matches anywhere.
"""
import concurrent.futures as cf, os, re, sys, time
from pathlib import Path

import tiktoken
from curl_cffi import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from givememd import read  # noqa: E402

OUT = Path(os.environ.get('GIVEMEMD_DATA', Path.home() / '.cache' / 'givememd')) / ('social_jev' if os.environ.get('GIVEMEMD_JEV') == '1' else 'social')
OUT.mkdir(parents=True, exist_ok=True)
enc = tiktoken.get_encoding('o200k_base')
NUM = r'[\d.,]+\s*[KkMm]?'

PAGES = {
    'insta_profile': ('https://www.instagram.com/nasa/', {
        'name': r'NASA', 'followers': NUM + r'\s*(followers|Followers)', 'posts_count': NUM + r'\s*(posts|Posts)',
        'post_links': r'instagram\.com/(p|reel)/[\w-]+'}),
    'insta_post': ('https://www.instagram.com/p/DPeI9qVkV5S/', {
        'author': r'nasa', 'caption_or_likes': r'(likes|comments|NASA)\b.{20,}'}),
    'tiktok_profile': ('https://www.tiktok.com/@nasa', {
        'name': r'NASA', 'followers': NUM + r'\s*(Followers|followers)', 'likes': NUM + r'\s*(Likes|likes)'}),
    'x_profile': ('https://x.com/NASA', {'name': r'NASA', 'followers': NUM + r'\s*(Followers|followers)'}),
    'threads_profile': ('https://www.threads.com/@nasa', {'name': r'NASA', 'followers': NUM + r'\s*followers'}),
    'youtube_video': ('https://www.youtube.com/watch?v=dQw4w9WgXcQ', {
        'title': r'Never Gonna Give You Up', 'channel': r'Rick Astley', 'views': r'[\d,.]+\s*[KMB]?\s*views',
        'description': r'(official|Official).{0,40}(video|Video)'}),
    'reddit_sub': ('https://www.reddit.com/r/LocalLLaMA/', {
        'name': r'LocalLLaMA', 'posts': r'(?s)(\d+\s*(comments|upvotes|votes)).*(\d+\s*(comments|upvotes|votes)).*(\d+\s*(comments|upvotes|votes))'}),
    'linkedin_post_profile': ('https://www.linkedin.com/in/williamhgates/', {
        'name': r'Bill Gates', 'headline': r'(Gates Foundation|Breakthrough Energy|Co-chair)'}),
    'facebook_page': ('https://www.facebook.com/NASA/', {'name': r'NASA', 'followers': NUM + r'\s*(followers|likes)'}),
    'pinterest_pin_board': ('https://www.pinterest.com/nasa/', {'name': r'NASA', 'followers': NUM + r'\s*(followers|monthly)'}),
    'medium_article': ('https://medium.com/@karpathy/software-2-0-a64152b37c35', {
        'title': r'Software 2\.0', 'author': r'Karpathy', 'body': r'neural network'}),
    'quora_q': ('https://www.quora.com/What-is-machine-learning', {'question': r'(?i)what is machine learning', 'answer': r'.{200,}'}),
}

GARBAGE = re.compile(r"(?i)log ?in to|sign up to see|something went wrong|enable javascript|blocked|captcha|"
                     r"continue shopping|page isn.t available|not available|you.ve been blocked|verify you are human")


def run_ours(url):
    t = time.time()
    try:
        md, r = read(url)
        return md or '', time.time() - t, (r.tier if md else 'FAIL: ' + ' | '.join(r.trace)[-160:])
    except Exception as e:
        return '', time.time() - t, f'error {e}'


def run_jina(url):
    t = time.time()
    try:
        r = requests.get('https://r.jina.ai/' + url, timeout=90)
        return r.text, time.time() - t, f'HTTP {r.status_code}'
    except Exception as e:
        return '', time.time() - t, f'error {e}'


def score(md, checks):
    return {k: bool(re.search(p, md)) for k, p in checks.items()}


def main():
    with cf.ThreadPoolExecutor(8) as ex:
        jobs = {(n, tool): ex.submit(fn, url) for n, (url, _) in PAGES.items() for tool, fn in (('givememd', run_ours), ('jina', run_jina))}
    tot = {'givememd': [0, 0, 0], 'jina': [0, 0, 0]}
    print(f"{'page':22}{'givememd':>30}{'jina':>30}")
    for n, (url, checks) in PAGES.items():
        row = f'{n:22}'
        for tool in ('givememd', 'jina'):
            md, sec, note = jobs[(n, tool)].result()
            (OUT / f'{n}__{tool}.md').write_text(md)
            s = score(md, checks)
            ok, tok = sum(s.values()), len(enc.encode(md))
            junk = ' wall?' if GARBAGE.search(md[:1500]) else ''
            tot[tool][0] += ok; tot[tool][1] += len(s); tot[tool][2] += tok
            row += f'{ok}/{len(s)} {tok:6}tok {sec:4.1f}s{junk:6}'.rjust(30)
            if '-v' in sys.argv:
                print(f'    {tool}: {note[:120]} missed={[k for k, v in s.items() if not v]}')
        print(row, flush=True)
    for tool, (ok, n, tok) in tot.items():
        print(f'{tool:10} checks {ok}/{n} ({ok / n:.0%})  total tokens {tok}')


if __name__ == '__main__':
    main()
