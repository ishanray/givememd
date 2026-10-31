/** givememd: turn any web page into clean, token-lean markdown for LLMs. */
import { convert } from './extract.js';
import { fetchPage, TIERS, UnsafeURL, type Result } from './fetch.js';

export { convert, type ConvertOptions } from './extract.js';
export { fetchPage, normalize, UnsafeURL, type Result } from './fetch.js';
export { pageStatus } from './decide.js';

/** Text after the frontmatter, without markdown punctuation. */
export function bodyText(md: string): string {
  const parts = md.split('---');
  const rest = parts.length >= 3 ? parts.slice(2).join('---') : md;
  return rest.replace(/[#*_`>|\-\s]+/g, ' ').trim();
}

/** Site-served markdown is often MDX: drop heading anchors and bare component tags, keep their content. */
export function cleanSiteMarkdown(md: string): string {
  return md.replace(/\s*\{\/\*.*?\*\/\}/g, '').replace(/^[ \t]*<\/?[A-Z][\w.]*(\s[^>]*)?\/?>[ \t]*\n/gm, '').replace(/\n{3,}/g, '\n\n');
}

export interface ReadOptions { links?: boolean; tiers?: string[] | null }

/** URL -> { markdown (null when every tier was blocked), result }. Throws UnsafeURL for private/invalid targets. */
export async function read(target: string, opts: ReadOptions = {}): Promise<{ markdown: string | null; result: Result }> {
  const { links = true, tiers = null } = opts;
  const r = await fetchPage(target, tiers);
  if (r.partial) return { markdown: convert(r.body, r.url, { links: false, metaOnly: true }), result: r };
  if (!r.ok) return { markdown: null, result: r };
  if (r.contentType.includes('markdown')) return { markdown: cleanSiteMarkdown(r.body), result: r };
  const md = convert(r.body, r.url, { links });
  const names = TIERS.map(([n]) => n);
  const later = names.includes(r.tier) ? names.slice(names.indexOf(r.tier) + 1) : [];
  if (later.length && bodyText(md).length < 200 && r.body.split('<script').length - 1 >= 3) {
    // the page "loaded" but its content is rendered by JavaScript: render it
    const r2 = await fetchPage(target, later, false);
    if (r2.ok && !r2.contentType.includes('markdown')) {
      const md2 = convert(r2.body, r2.url, { links });
      if (bodyText(md2).length > bodyText(md).length) {
        r2.trace = [...r.trace, 'extraction was empty; rendered', ...r2.trace];
        return { markdown: md2, result: r2 };
      }
    }
  }
  return { markdown: md, result: r };
}

export { UnsafeURL as UnsafeUrlError };
