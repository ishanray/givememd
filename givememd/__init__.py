import re

from .extract import convert
from .fetch import TIERS, UnsafeURL, fetch


def read(target, links=True, tiers=None):
    """URL -> (markdown, Result). Raises UnsafeURL for private/invalid targets."""
    r = fetch(target, tiers=tiers)
    if r.partial:
        return convert(r.body, r.url, links=False, meta_only=True), r
    if not r.ok:
        return None, r
    if 'markdown' in r.content_type:
        return clean_site_markdown(r.body), r
    md = convert(r.body, r.url, links=links)
    later = [n for n, _ in TIERS[[n for n, _ in TIERS].index(r.tier) + 1:]] if r.tier in [n for n, _ in TIERS] else []
    if later and len(body_text(md)) < 200 and r.body.count('<script') >= 3:
        # the page "loaded" but its content is rendered by JavaScript (streamed payloads, app shells): render it
        r2 = fetch(target, tiers=later, use_cache=False)
        if r2.ok and 'markdown' not in r2.content_type:
            md2 = convert(r2.body, r2.url, links=links)
            if len(body_text(md2)) > len(body_text(md)):
                r2.trace = r.trace + ['extraction was empty; rendered'] + r2.trace
                return md2, r2
    return md, r


def clean_site_markdown(md):
    """Site-served markdown is often MDX: drop heading anchors and bare component tags, keep their content."""
    md = re.sub(r'\s*\{/\*.*?\*/\}', '', md)
    md = re.sub(r'(?m)^[ \t]*</?[A-Z][\w.]*(\s[^>]*)?/?>[ \t]*\n', '', md)
    return re.sub(r'\n{3,}', '\n\n', md)


def body_text(md):
    """Text after the frontmatter, without markdown punctuation."""
    parts = md.split('---', 2)
    return re.sub(r'[#*_`>|\-\s]+', ' ', parts[2] if len(parts) == 3 else md).strip()
