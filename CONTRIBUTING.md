# Contributing

Thanks for helping. A few things keep quality measurable:

1. **Tests:** `pip install -e ".[dev,mcp]"`, then `pytest` (offline). Add a test for every behavior you change.
   Fixtures must be synthetic: don't commit other sites' pages.
2. **Measure extraction changes.** Build the page cache (`python bench/fetch_pages.py`), then compare
   `python bench/regress.py` and `python eval/run.py --variants default` before and after. Report facts, tokens and
   junk leaked in the PR. A change that adds facts but also junk needs a strong reason.
3. **Site fixes should be generic.** Prefer a rule that explains why a site broke (a React streaming pattern, a hidden
   tab panel) over a selector for one domain. If a site truly needs special handling, say so in the PR.
4. **Fetch politely.** Benchmarks fetch real sites: one request at a time per site, and back off on 429.
