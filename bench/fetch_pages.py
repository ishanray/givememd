"""Build the local page cache the benchmarks read (other sites' content is never committed).

    python bench/fetch_pages.py [--force] [name ...]

Fetches each manifest page (bench/answers PAGES) with givememd's own fetch ladder into $GIVEMEMD_DATA/pages
(default ~/.cache/givememd/pages). Pages change over time, so answer keys are rebuilt from whatever you fetch; the
hand-labeled gold snippets in eval/gold were taken from 2026-10-30 versions and some will no longer match.
"""
import argparse, sys, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT)]
from bench.answers import PAGES  # noqa: E402
from bench.answers.cache import PAGES_DIR  # noqa: E402
from givememd.fetch import fetch  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('names', nargs='*')
    ap.add_argument('--force', action='store_true')
    a = ap.parse_args()
    PAGES_DIR.mkdir(parents=True, exist_ok=True)
    for name in a.names or PAGES:
        p = PAGES_DIR / f'{name}.html'
        if p.exists() and not a.force:
            print(f'{name:16} cached'); continue
        r = fetch(PAGES[name], use_cache=False)
        if r.ok:
            p.write_text(r.body)
            print(f'{name:16} ok via {r.tier:10} {len(r.body):8} bytes')
        else:
            print(f'{name:16} FAILED: {" | ".join(r.trace)[-120:]}')
        time.sleep(1)


if __name__ == '__main__':
    main()
