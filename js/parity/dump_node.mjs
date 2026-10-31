// Write Node conversions for a manifest of pages: node parity/dump_node.mjs <manifest.json> <outdir>
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { convert } from '../dist/index.js';
const [manifest, outdir] = process.argv.slice(2);
mkdirSync(outdir, { recursive: true });
const pages = JSON.parse(readFileSync(manifest, 'utf8'));
let n = 0, failed = 0;
for (const p of pages) {
  const buf = readFileSync(p.path);
  const html = p.path.endsWith('.gz') ? gunzipSync(buf).toString('utf8') : buf.toString('utf8');
  try { writeFileSync(`${outdir}/${p.name}.md`, convert(html, p.url, { links: false })); n++; }
  catch (e) { failed++; writeFileSync(`${outdir}/${p.name}.md`, `ERROR ${e.message}`); }
}
console.log(`node: ${n} converted, ${failed} failed`);
