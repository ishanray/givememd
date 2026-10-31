"""Smaller websites: a stratified random sample from deep in the Tranco list (fixed seed, reproducible).

    python bench/top/longtail.py --tranco <top-1m.csv> --out <dir>

Bands (rank range -> sites wanted): 2,001-10k: 200 · 10k-50k: 250 · 50k-200k: 250 · 200k-1M: 300.
Same name filters and homepage probe as domains.py; a band keeps drawing candidates until it has enough real websites.
Writes <out>/domains.json in the format run.py expects (source = 'longtail', band recorded per domain).
"""
import argparse, concurrent.futures as cf, json, random, sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from domains import ADULT, INFRA, INFRA_SUFFIX, probe, tranco  # noqa: E402

BANDS = [(2001, 10_000, 200), (10_001, 50_000, 250), (50_001, 200_000, 250), (200_001, 1_000_000, 300)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--tranco', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--seed', type=int, default=20261030)
    a = ap.parse_args()
    rng = random.Random(a.seed)
    allrows = [(r, d) for r, d in tranco(a.tranco, 1_000_000) if not (ADULT.search(d) or INFRA.search(d) or INFRA_SUFFIX.search(d))]
    rows, stats = [], {}
    with cf.ThreadPoolExecutor(48) as ex:
        for lo, hi, want in BANDS:
            pool = [x for x in allrows if lo <= x[0] <= hi]
            rng.shuffle(pool)
            kept, tried, i = [], 0, 0
            while len(kept) < want and i < len(pool):
                batch = pool[i:i + want]; i += want
                for (rank, d), p in zip(batch, ex.map(probe, [d for _, d in batch])):
                    tried += 1
                    if p['keep'] and len(kept) < want:
                        kept.append({'domain': d, 'source': 'longtail', 'band': f'{lo}-{hi}', 'rank': rank, **p})
            rows += kept
            stats[f'{lo}-{hi}'] = {'kept': len(kept), 'probed': tried,
                                   'walls': sum(1 for k in kept if k['why'].startswith('wall'))}
            print(f'band {lo}-{hi}: kept {len(kept)} of {tried} probed ({stats[f"{lo}-{hi}"]["walls"]} walled)', flush=True)
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out / 'domains.json').write_text(json.dumps({'tranco_list_id': 'PYK6J', 'seed': a.seed, 'bands': stats, 'domains': rows}, indent=1))
    print(f'longtail: {len(rows)} domains')


if __name__ == '__main__':
    main()
