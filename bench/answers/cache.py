"""Where benchmark pages live. They are other sites' content, so they are never committed: build the cache with
`python bench/fetch_pages.py` (it fetches every page in the manifest) or point GIVEMEMD_DATA at an existing one."""
import os
from pathlib import Path

DATA = Path(os.environ.get('GIVEMEMD_DATA', Path.home() / '.cache' / 'givememd'))
PAGES_DIR = DATA / 'pages'


def html(name):
    p = PAGES_DIR / f'{name}.html'
    if not p.exists():
        raise FileNotFoundError(f'{p} missing: run `python bench/fetch_pages.py` (or set GIVEMEMD_DATA)')
    return p.read_text(encoding='utf-8', errors='ignore')
