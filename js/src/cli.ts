#!/usr/bin/env node
/** givememd <url> [--no-links] [--trace]   -- print LLM-ready markdown for a web page (fetched from this machine). */
import { read, UnsafeURL } from './index.js';

const USAGE = 'givememd <url> [--no-links] [--trace]   -- print LLM-ready markdown for a web page (fetched from this machine).';

async function main() {
  const argv = process.argv.slice(2);
  const args = argv.filter((a) => !a.startsWith('--') && a !== '-h');
  if (argv.includes('--help') || argv.includes('-h')) { console.log(USAGE); return; }
  if (!args.length) { console.error(USAGE); process.exit(2); }
  try {
    const { markdown, result } = await read(args[0], { links: !argv.includes('--no-links') });
    if (argv.includes('--trace')) console.error(result.trace.join('\n'));
    if (markdown === null) { console.error(`could not read ${result.url}`); process.exit(1); }
    process.stdout.write(markdown);
  } catch (e) {
    if (e instanceof UnsafeURL) { console.error(`refused: ${e.message}`); process.exit(1); }
    throw e;
  }
}
main();
