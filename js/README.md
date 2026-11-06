# givememd (Node)

Turn any web page into clean, token-lean markdown for LLMs. This is the Node/TypeScript port of givememd
(`pip install givememd` for Python). It produces the same output as the Python package; a parity test enforces that.

```sh
npx givememd https://www.zillow.com/homes/Austin,-TX_rb/
```

## Install
```sh
npm i givememd
```
JavaScript-heavy pages work out of the box. givememd drives an installed Chrome, Edge, Brave or Chromium headlessly.
If none is installed, it downloads Playwright's headless Chromium once, on the first page that needs it (about 100 MB
download, 200 MB on disk). `GIVEMEMD_CHROME` picks a browser; `GIVEMEMD_NO_BROWSER_DOWNLOAD=1` disables the download.
The browser stays warm between requests in the MCP and HTTP servers.
Optional: [Lightpanda](https://github.com/lightpanda-io/browser), a fast headless browser, as a middle tier. Install it
separately (AGPL, not bundled) and set `GIVEMEMD_LIGHTPANDA=/path/to/lightpanda`.

## Use
**CLI:** `npx givememd <url> [--no-links] [--trace]`

**MCP** (fetches from your own machine):
```sh
claude mcp add givememd -- npx -y givememd-mcp
```
It provides one tool, `read_url(url, links?)`.

**HTTP server (local):** `npx givememd-server --port 8787`, then `curl http://127.0.0.1:8787/en.wikipedia.org/wiki/Markdown`

**Library:**
```js
import { read, convert } from 'givememd';
const { markdown, result } = await read('https://docs.python.org/3/library/pathlib.html');
console.log(result.tier, markdown);
const md = convert(html, 'https://example.com/page', { links: false });   // HTML you already have
```

## How it works
- **Fetch ladder:** a plain request with a browser TLS fingerprint (via [impit](https://github.com/apify/impit)), then
  Lightpanda, then headless Chromium. Each step runs only when the previous one hit a bot wall or an empty JS shell.
- **Bot-wall and login-wall detection:** a walled page is never passed off as content.
- **Extraction:** embedded app data becomes tables; menus and hidden UI are dropped; headlines are kept; React-streamed
  content is recovered.

See the repository README for details and benchmarks.

## Differences from the Python package
- **No component mode or Jev integration** yet. These are experimental in Python.
- **SSRF.** Each hop is checked before it is fetched (public addresses only, ports 80/443, redirects re-checked).
  impit resolves names itself, so a small DNS-rebinding window remains. Set `GIVEMEMD_STRICT_SSRF=1` to use Node's
  https with the checked address pinned (no browser fingerprint). Read SECURITY.md before running a public server.
- **Output parity.** On 300 real top-site pages, 97.3% of outputs are byte-identical to Python's, and line similarity
  is 0.999. Pages built from many link-heavy blocks can tip a pruning decision differently. JSON numbers like `2.0`
  print as `2`.

## License
MIT
