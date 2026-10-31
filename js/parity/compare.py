"""Python vs Node parity: python js/parity/compare.py <manifest.json> <workdir>

Converts every page with the Python package and reads the Node outputs from <workdir>/node (written by
dump_node.mjs), then reports exact matches, line similarity, and answer-key recall where keys exist."""
import difflib, gzip, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT)]
from givememd.extract import convert  # noqa: E402

manifest, work = Path(sys.argv[1]), Path(sys.argv[2])
pages = json.loads(manifest.read_text())
try:
    from bench.answers import PAGES as KEYED, facts, norm_for
except Exception:
    KEYED = {}
exact, sims, worst, rec = 0, [], [], {'py': [], 'node': []}
for p in pages:
    raw = Path(p['path']).read_bytes()
    html = (gzip.decompress(raw) if p['path'].endswith('.gz') else raw).decode('utf-8', 'replace')
    py = convert(html, p['url'], links=False)
    node = (work / 'node' / f"{p['name']}.md").read_text()
    if py == node:
        exact += 1; sims.append(1.0); continue
    a, b = py.splitlines(), node.splitlines()
    s = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    sims.append(s); worst.append((s, p['name'], next((f'py: {x!r}\n      node: {y!r}' for x, y in zip(a, b) if x != y), 'length differs')))
    if p.get('keys') and p['name'] in KEYED:
        nf = norm_for(p['name'])
        alts = lambda v: [nf(str(x)) for x in (v if isinstance(v, (tuple, list)) else (v,)) if nf(str(x))]
        F = [v for _, v in facts(p['name']) if alts(v)]
        for k, md in (('py', py), ('node', node)):
            rec[k].append(sum(1 for v in F if any(x in nf(md) for x in alts(v))) / max(len(F), 1))
n = len(pages)
print(f'{n} pages: exact match {exact}/{n} ({exact / n:.1%}), mean line similarity {sum(sims) / n:.3f}, '
      f'>= 0.95 similar: {sum(1 for s in sims if s >= 0.95)}/{n}')
if rec['py']:
    print(f"answer-key recall on differing keyed pages: python {sum(rec['py']) / len(rec['py']):.1%}  node {sum(rec['node']) / len(rec['node']):.1%}")
for s, name, d in sorted(worst)[:8]:
    print(f'  {s:.3f} {name}\n      {d[:300]}')
