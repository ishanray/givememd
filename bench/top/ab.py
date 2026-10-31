"""A/B two extractor versions on saved top-site pages: facts recovered (from raw HTML) vs tokens spent.

    python bench/top/ab.py <extract_A.py> <extract_B.py> --data <crawl dir from run.py> [--n 300]

Samples a fixed random set of top-site URLs plus the URLs where we lose to Jina on recall, re-extracts each page with
both versions, and reports mean ref recall and tokens for each, and facts gained per 1k extra tokens.
"""
import gzip, importlib.util, json, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent)); sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from score import body, enc, norm, ref_facts, text_of, usable  # noqa: E402



def load(path, name):
    spec = importlib.util.spec_from_file_location(f'givememd.{name}', path, submodule_search_locations=None)
    m = importlib.util.module_from_spec(spec); m.__package__ = 'givememd'
    spec.loader.exec_module(m); return m


def main():
    a, b = load(sys.argv[1], 'ext_a'), load(sys.argv[2], 'ext_b')
    n = int(sys.argv[sys.argv.index('--n') + 1]) if '--n' in sys.argv else 300
    S = Path(sys.argv[sys.argv.index('--data') + 1])
    R = [json.loads(l) for l in open(S / 'score_vs_jina.jsonl')]
    rng = random.Random(11)
    sample = rng.sample(R, min(n, len(R)))
    losses = [r for r in R if r['vs_jina'] == 'loss' and r['vs_jina_why'] == 'recall'][:120]
    for label, rows in (('random sample', sample), ('recall losses to jina', losses)):
        tot = {'a': [0, 0, 0], 'b': [0, 0, 0]}; pages = 0
        for r in rows:
            d = S / 'runs' / r['domain']
            hp = d / f"{r['which']}__ours.html.gz"
            if not hp.exists(): continue
            o = json.loads((d / f"{r['which']}__ours.json").read_text())
            if o.get('markdown_native'): continue
            html = gzip.decompress(hp.read_bytes()).decode('utf-8', 'replace')
            F = ref_facts(html)
            if not F: continue
            pages += 1
            for k, m in (('a', a), ('b', b)):
                md = m.convert(html, o.get('final', r['url']), links=False)
                t = norm(text_of(body('ours', md)))
                tot[k][0] += sum(1 for f in F if f in t) / len(F)
                tot[k][1] += len(enc.encode(body('ours', md)))
                tot[k][2] += usable('ours', md)
        ra, rb = tot['a'][0] / pages, tot['b'][0] / pages
        ta, tb = tot['a'][1] / pages, tot['b'][1] / pages
        print(f'{label} ({pages} pages):  A recall {ra:.1%} tokens {ta:.0f} usable {tot["a"][2] / pages:.1%}  |  '
              f'B recall {rb:.1%} tokens {tb:.0f} usable {tot["b"][2] / pages:.1%}  |  '
              f'recall {100 * (rb - ra):+.1f} pts, tokens {100 * (tb - ta) / ta:+.1f}%')


if __name__ == '__main__':
    main()
