# givememd

Turn any web page into clean, token-lean markdown for LLMs.

```sh
givememd https://www.zillow.com/homes/Austin,-TX_rb/
```

givememd fetches the page (escalating from a plain request to a headless browser only when needed), works out
what is content and what is chrome, and returns markdown that keeps the facts and drops the noise: listings hidden in
a page's app state become tables, menus and cookie banners disappear, and walled pages are reported as walled instead of
being passed off as content.

## Install

```sh
pip install givememd                       # core: fetch + extract
pip install "givememd[browser]"            # + headless Chromium tier
python -m playwright install chromium-headless-shell
pip install "givememd[mcp]"                # + MCP server for Claude / other agents
```

Optional: [Lightpanda](https://github.com/lightpanda-io/browser), a fast headless browser, as a middle tier. Install it
separately (it is AGPL-licensed and not bundled) and set `GIVEMEMD_LIGHTPANDA=/path/to/lightpanda`.

## Use

**CLI**
```sh
givememd https://react.dev/reference/react/useState          # markdown to stdout
givememd amazon.com/dp/B0D1XD1ZV3 --no-links --trace          # trace shows which fetch tier was needed
```

**MCP** (runs on your machine, so pages are fetched from your own connection)
```sh
claude mcp add givememd -- uvx --from 'givememd[mcp]' givememd-mcp
```
It exposes one tool, `read_url(url, links=True)`.

**HTTP server** (the `givememd.com/<url>` shape)
```sh
givememd-server --port 8787
curl http://127.0.0.1:8787/en.wikipedia.org/wiki/Markdown
curl "http://127.0.0.1:8787/https://react.dev/reference/react/useState?links=0"
```
Responses carry `X-Givememd-Tier`, `X-Givememd-Tokens`, `X-Givememd-Source` and `X-Givememd-Partial`.
The bundled server is for local use; see [SECURITY.md](SECURITY.md) before exposing anything publicly.

**Python**
```python
from givememd import read
md, result = read("https://docs.python.org/3/library/pathlib.html")
print(result.tier, md[:500])
```

## How it works

1. **Fetch ladder.** A plain HTTP request with a browser-like TLS fingerprint (asking for `text/markdown` first; sites
   that serve their own markdown are passed through) → Lightpanda → headless Chromium. A tier is skipped unless the previous
   one got a bot wall, an empty JavaScript shell, or a page whose content only appears after rendering.
2. **Is this real content?** Every response is classified `ok` / `blocked` / `needs_js`: vendor challenge markers
   (Cloudflare, DataDome, AWS WAF, PerimeterX…), login walls, block statuses, empty shells. When every tier hits a wall,
   givememd returns only the page's own metadata, marked `partial:`, rather than a login form.
3. **Extraction.**
   - Metadata and JSON-LD go into a compact frontmatter.
   - Record arrays embedded in the page (Next.js state, JSON-LD lists) become markdown tables. Variants (colorways, sizes)
     collapse into one row per item, and opaque IDs are dropped.
   - The DOM is pruned of chrome and hidden UI. Collapsed "see more" content, tab panels and React-streamed segments are kept.
   - Link-heavy blocks keep their headlines as one compact line and lose their menu labels.
   - The result is de-duplicated, interface text is removed, links are cleaned of tracking parameters, and listing cards
     render as single lines.
4. **Optional component mode** (`convert(..., mode='components-light')`, experimental). The page is split into small
   sections, each matched to one of 121 catalog components (product header, spec table, recipe, FAQ, navigation…). Each
   section is filled and rendered with a fixed layout, so similar pages read the same way. Labels come from rules, plus
   optionally [TypeSafe](https://typesafe.ai)'s Jev decision model (`GIVEMEMD_JEV=1` and `TYPESAFE_API_KEY`).

## How it compares

Measured on 2026-10-30 against Jina Reader (`r.jina.ai`, no key) and defuddle.md. Each tool was run on the same URLs:
a homepage plus one inner page per site, fetched from one datacenter IP. Details and caveats are in
[docs/BENCHMARK.md](docs/BENCHMARK.md).

| Set | URLs | givememd vs Jina (win / tie / loss) | givememd vs defuddle (win / tie / loss) | Median tokens: givememd vs Jina |
|---|---|---|---|---|
| Top sites (Tranco top 2,000 + AI-cited) | 3,584 | 66 / 15 / 19% | 74 / 20 / 6% | 1,034 vs 4,135 |
| Smaller sites (Tranco ranks 2k–1M) | 795 | 65 / 15 / 20% | 76 / 18 / 7% | 1,027 vs 4,525 |
| Indie blogs (Kagi Small Web) | 64–300 | 58 / 39 / 3% | 42 / 56 / 2% | 1,059 vs 1,365 |

These scores are automatic. A page counts as "usable" if it has real content rather than a wall or an error, judged by
the same check for every tool. Facts are recall of titles, headings, paragraph sentences and JSON-LD from the raw page,
plus sentences that at least two tools agree on. Most of our remaining losses are bot walls against a datacenter IP,
and portal pages where keeping every menu scores more facts.

## Develop

```sh
pip install -e ".[dev,mcp,browser]"
pytest                          # offline unit tests
pytest -m live                  # end-to-end: CLI, HTTP server and MCP over stdio, against the real web
python bench/fetch_pages.py     # build the local page cache (other sites' pages are never committed)
python bench/regress.py         # answer-key recall and tokens on 25 pages
python eval/run.py -v           # 19 hand-labeled pages: content lost, junk leaked, fields, component labels
```
The large benchmark (top, smaller and indie sites against competitors) lives in `bench/top/`; see
[docs/BENCHMARK.md](docs/BENCHMARK.md). Contributions are welcome; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Roadmap

- A browser extension and a relay that lets cloud agents fetch through their owner's browser. This is how bot-walled
  and logged-in pages become readable without proxies.
- A hosted `givememd.com/<url>` with caching.
- Caching component labels per site layout, so model-assisted labeling costs almost nothing per page.

## License

Apache-2.0. Lightpanda (AGPL) and Chromium are optional and installed separately; Jev is an optional third-party API.
Product names in the benchmark belong to their owners.
