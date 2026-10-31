# Benchmark

Everything here can be re-run. Pages are other sites' content, so they are never committed; scripts fetch them
into `$GIVEMEMD_DATA` (default `~/.cache/givememd`).

## 1. Answer-key pages (`bench/regress.py`)
25 pages, in four sets:
- **tuning:** Amazon, Zillow, LinkedIn and react.dev, which the extractor was developed on.
- **held-out and fresh:** Wikipedia, GitHub, Python docs, MDN, the Guardian, Ars Technica, a Substack post, Allbirds,
  discuss.python.org.
- **stress:** link-list pages.
- **data:** pages whose content lives in embedded JSON: Redfin, Airbnb, Walmart, Nike, IKEA, Eventbrite, BBC Good Food,
  Goodreads.

Answer keys (`bench/answers/`) are built from each page's raw HTML (DOM selectors, JSON-LD, embedded state) before
looking at any output. The score is recall of those facts, plus tokens and layout checks.

## 2. Hand-labeled pages (`eval/run.py`, `eval/gold/`)
- **Labels:** 19 pages with 611 sections, each labeled with one of the 121 catalog components, plus 78 header fields
  (price, author, date…). Labeled from the raw pages by a pass that never saw the classifier. 180 sections list
  acceptable alternatives. See `eval/gold/README.md`.
- **Metrics:** content lost (gold content sections missing from the output), junk leaked (gold chrome sections
  present), fields found, page type, keep/drop and layout agreement, component-label accuracy, Jev cost.
- **Caveat:** labels were made on 2026-10-30 versions of the pages. Pages fetched later may have changed, and some
  snippets will no longer match.

## 3. Large comparison vs other tools (`bench/top/`)
- **Sets:**
  - **top:** Tranco list `PYK6J` top 2,000 real websites, plus 26 AI-cited domains. Infrastructure and adult domains
    are removed by name, then homepages are probed (`domains.py`).
  - **smaller:** 1,000 domains sampled at random, stratified across Tranco ranks 2k–1M (`longtail.py`).
  - **indie:** latest posts from Kagi's Small Web feed list (`indie.py`). Marginalia results are optional; its public
    API key is often rate-limited.
- **Crawl** (`run.py`): each site's homepage plus one inner content page, fetched with the full ladder (raw HTML
  saved). Then Jina Reader (no key, throttled to 18 requests/min) and defuddle.md are run on the same URLs.
- **Scoring** (`score.py`, no hand labels), applied identically to every tool's markdown:
  - **usable:** at least 200 characters of text, with no wall, login or error page in the first 1,500 characters.
  - **ref recall:** title, description, h1–h3, `<p>` sentences and JSON-LD strings from the raw page.
  - **consensus recall:** sentences that at least two tools' outputs contain. Only meaningful with three tools.
  - **tokens:** o200k.
- **Outcome per URL:** usable beats unusable. Otherwise more than 5 points of mean recall wins. Otherwise more than
  15% fewer tokens wins. Otherwise it's a tie.

### Results (2026-10-30)
| Set | URLs | vs Jina (win / tie / loss) | vs defuddle (win / tie / loss) | Usable: givememd / Jina | Facts: givememd / Jina | Median tokens |
|---|---|---|---|---|---|---|
| Top | 3,584 (Jina) · 1,059 (defuddle) | 66.0 / 14.6 / 19.4% | 73.6 / 20.1 / 6.3% | 84.5 / 84.7% | 73.6 / 62.1% | 1,034 / 4,135 |
| Smaller | 795 · 493 | 65.0 / 14.7 / 20.3% | 75.5 / 18.1 / 6.5% | 86.9 / 89.2% | 74.5 / 65.0% | 1,027 / 4,525 |
| Indie | 64 · 300 | 57.8 / 39.1 / 3.1% | 41.7 / 56.0 / 2.3% | 93.8 / 92.2% | 81.9 / 70.8% | 1,059 / 1,365 |

**Caveats**
- **Coverage:** runs were stopped once the samples were large enough. Jina covered 45% of the smaller set and 21% of
  the indie set; defuddle was stopped when it began rate-limiting.
- **One datacenter IP:** every tool was fetched from it. Bot walls (Cloudflare, DataDome, Akamai, login walls) block
  about 7% of top-site URLs for us; a home IP or the planned browser-relay mode changes that.
- **Failed requests:** competitor requests that failed on our side (DNS errors, timeouts) were retried, not counted
  against the competitor.
- **What the facts metric measures:** recall of text facts, so it undervalues tables, and it rewards tools that keep
  menus on portal pages.

## Making changes
- **A/B before shipping:** `bench/top/ab.py <old_extract.py> <new_extract.py> --data <crawl dir>` re-extracts saved
  pages with both versions and reports facts vs tokens.
- **Guardrails:** run `bench/regress.py` and `eval/run.py`, and treat a rise in junk leaked as a regression even if
  facts go up.
- **History:** several plausible ideas were rejected this way:
  - Dropping CSS-framework `hidden` classes removed real tab content.
  - Always using the whole `<body>` raised junk from 21% to 27%.
