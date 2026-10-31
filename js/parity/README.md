# Python ↔ Node parity

- **CI (`npm test`):** `js/test/parity.test.mjs` requires byte-identical output to the Python package on the synthetic
  fixtures in `tests/fixtures`.
- **Regenerating goldens:** after an intentional change to either implementation, update both, then regenerate:
  ```sh
  python -c "from pathlib import Path; from givememd.extract import convert; [Path('js/test/golden', p.stem + '.md').write_text(convert(p.read_text(), 'https://fixture.example/', links=True)) for p in Path('tests/fixtures').glob('*.html')]"
  ```
- **Real pages (local):**
  1. Write a manifest: a JSON list of `{name, path, url}`, where paths may be `.html` or `.html.gz` (for example, the
     page cache from `bench/fetch_pages.py`, or a crawl from `bench/top/run.py`).
  2. Run:
     ```sh
     node js/parity/dump_node.mjs manifest.json work/node
     python js/parity/compare.py manifest.json work
     ```
- **Results (2026-10-30):**
  - fixtures: 7/7 identical
  - 25 answer-key pages: 25/25 identical
  - 300 random top-site pages: 292/300 identical (mean line similarity 0.999)
