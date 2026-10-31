"""Component pipeline: segment the page finely, label each section with a catalog component, fill, render.

    segments(root)          -> Segment list in reading order (small, single-purpose sections)
    page_type(...)          -> one catalog category for the whole page (JSON-LD, else Jev, else rules)
    label(...)              -> a component per segment: confident rules first, Jev for the rest
    render(...)             -> markdown: components drawn with fixed layouts, junk dropped, same-kind runs merged

Turned on with convert(..., mode='components') or GIVEMEMD_COMPONENTS=1. Without a Jev key it still runs, with
rules-only labels (coarser: anything unclear is kept as generic prose).
"""
import hashlib, re
from collections import Counter
from dataclasses import dataclass, field

from . import datatables, jev
from .components import BY_CATEGORY, BY_LD, BY_NAME, CATEGORIES, CATALOG

DROP_CONFIDENCE = float(__import__('os').environ.get('GIVEMEMD_DROP_CONFIDENCE', '0.7'))            # a model must be this sure before content is thrown away; otherwise it is kept
MAXSEG = 700                      # a section bigger than this is split into its children
LEAF = {'table', 'pre', 'ul', 'ol', 'dl'}
LEAF_MAX = 6000
HEADING = re.compile(r'^#{1,6} ')
FACT = re.compile(r'^[-\s]*([$€£¥₹]\s?[\d,.]+|[\d.]+ out of 5|\(?[\d,]+\)? ?(ratings|reviews)|[\d.]+ ?stars?)\b', re.I)
KV = re.compile(r'^- ?[^:]{1,40}: \S')
GENERIC = ['article_body', 'doc_prose', 'encyclopedia_section', 'data_table', 'image_caption', 'related_articles',
           'see_also', 'faq', 'breadcrumb', 'key_takeaways', 'callout_note', 'code_example']
PROSE_FOR = {'article': 'article_body', 'docs': 'doc_prose', 'reference': 'encyclopedia_section', 'community': 'post_body',
             'commerce': 'product_description', 'food_health': 'article_body', 'business': 'article_body'}
KV_FOR = {'commerce': 'spec_table', 'reference': 'infobox', 'docs': 'parameter_list', 'profile': 'contact_info'}
LD_CATEGORY = {'Product': 'commerce', 'NewsArticle': 'article', 'Article': 'article', 'BlogPosting': 'article',
               'Recipe': 'food_health', 'Event': 'events_travel', 'JobPosting': 'listings', 'ItemList': 'listings',
               'QAPage': 'community', 'DiscussionForumPosting': 'community', 'VideoObject': 'media', 'Movie': 'media',
               'Book': 'media', 'Person': 'profile', 'ProfilePage': 'profile', 'Organization': 'profile',
               'LocalBusiness': 'profile', 'SoftwareSourceCode': 'docs', 'TechArticle': 'docs', 'FAQPage': 'business',
               'Hotel': 'events_travel', 'SingleFamilyResidence': 'listings'}


# when a page carries several JSON-LD entities, the main one is the most specific
LD_PRIORITY = ['Product', 'Recipe', 'Event', 'JobPosting', 'NewsArticle', 'BlogPosting', 'Article', 'TechArticle', 'QAPage',
               'DiscussionForumPosting', 'Movie', 'Book', 'Hotel', 'SingleFamilyResidence', 'SoftwareSourceCode', 'LocalBusiness',
               'Person', 'ProfilePage', 'VideoObject', 'FAQPage', 'ItemList', 'Organization']


def _types(o):
    t = o.get('@type')
    return t if isinstance(t, list) else [t]


def main_entities(ld):
    rank = lambda o: min((LD_PRIORITY.index(t) for t in _types(o) if t in LD_PRIORITY), default=len(LD_PRIORITY))
    return sorted(ld, key=rank)


# types that sites attach to almost any page; they don't say what the page is
WEAK_LD = {'Organization', 'ItemList', 'Person', 'VideoObject', 'Article', 'FAQPage', 'WebPage', 'WebSite', 'BreadcrumbList'}
PROSE_KINDS = ['article_body', 'subheading_section', 'doc_prose', 'encyclopedia_section', 'post_body', 'answer', 'review_item',
               'product_description', 'callout_note', 'author_bio', 'testimonial', 'pull_quote', 'image_caption', 'medical_info',
               'api_signature', 'parameter_list', 'return_value', 'transcript', 'related_articles', 'promo_ad', 'login_prompt', 'ui_chrome']


@dataclass
class Segment:
    blocks: list                  # markdown blocks (from extract.MD)
    tag: str = ''
    links: list = field(default_factory=list)
    label: str = ''
    how: str = ''                 # 'rule:<name>' | 'jev' | 'default'
    confidence: float = 1.0

    @property
    def text(self):
        return ' '.join(re.sub(r'^#+ |^- ', '', b) for b in self.blocks)


# ---------- segmentation ----------
def segments(root, url):
    from .extract import MD
    out = []

    def emit(nodes, tag):
        md = MD(url)
        for n in nodes:
            md.handle(n)
        md.flush()
        if md.blocks:
            out.append(Segment(md.blocks, tag, md.links))

    def rec(node):
        run = []                                   # consecutive inline children (text, <span>, <a>...)
        for c in node.iter(include_text=True):
            if c.tag == '-text' or c.tag in ('span', 'a', 'b', 'strong', 'em', 'i', 'code', 'small', 'label', 'sup', 'sub', 'br'):
                run.append(c); continue
            if run:
                emit(run, 'inline'); run = []
            text = c.text(separator=' ')
            n = len(re.sub(r'\s+', ' ', text).strip())
            if n == 0:
                continue
            if c.tag in LEAF and n <= LEAF_MAX or c.tag in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6'):
                emit([c], c.tag); continue
            if n <= MAXSEG and not _mixed(c, url):
                emit([c], c.tag); continue
            rec(c)
        if run:
            emit(run, 'inline')

    rec(root)
    return _attach_headings(out)


def _mixed(node, url):
    """A small box that holds a price/rating fact next to other text (Amazon: price + Visa promo) is split."""
    from .extract import MD
    md = MD(url); md.walk(node); md.flush()
    return len(md.blocks) > 1 and any(FACT.match(b) for b in md.blocks) and any(len(b) > 60 for b in md.blocks) \
        and node.css_first('div,span,p,li') is not None


def _attach_headings(segs):
    """A heading on its own belongs to the section that follows it."""
    out, pending = [], []
    for s in segs:
        if all(HEADING.match(b) for b in s.blocks):
            pending += s.blocks; continue
        if pending:
            if len(pending) >= 3:              # a stack of empty headings (tab labels, "step 1..11") says nothing
                pending = pending[-1:]
            s.blocks = pending + s.blocks; pending = []
        out.append(s)
    if pending:
        out.append(Segment(pending, 'h'))
    for s in out:                              # the same rule inside one section
        blocks, run = [], []
        for b in s.blocks + ['']:
            if b and HEADING.match(b):
                run.append(b); continue
            blocks += run[-1:] if len(run) >= 3 else run
            run = []
            if b: blocks.append(b)
        s.blocks = blocks
    return out


# ---------- labeling ----------
def page_type(meta, ld, segs, tables, judge):
    counts = Counter(t for o in ld for t in _types(o) if t)
    repeated = [t for t, n in counts.items() if n >= 3 and t not in ('ListItem', 'BreadcrumbList', 'Question', 'Answer')]
    if repeated:                                   # many Events / Products / homes on one page = a listing
        return 'listings', f'ld:{repeated[0]}x{counts[repeated[0]]}'
    for o in main_entities(ld):
        for t in _types(o):
            if t in LD_CATEGORY and t not in WEAK_LD:
                return LD_CATEGORY[t], f'ld:{t}'
    if judge:
        state = f"Web page: {meta.get('title', '')}\nURL: {meta.get('url', '')}\nOpening text: " + ' '.join(s.text for s in segs)[:1500]
        a = judge.ask(state, {'page': {'type': 'choice', 'instructions': 'What kind of web page is this?',
                                       'criteria': {k: v for k, v in CATEGORIES.items() if k != 'chrome'}}})
        if a: return a['page']['choice'], 'jev'
    if tables and len(tables[0].recs) >= 8: return 'listings', 'rule:table'
    if sum(1 for s in segs if s.tag == 'pre') >= 3: return 'docs', 'rule:code'
    return 'article', 'default'


def _rule(s, ptype):
    """Confident labels that need no model. Returns a component name or None."""
    from .extract import UI_TEXT, DATA_MARK
    body = [b for b in s.blocks if not HEADING.match(b)]
    if any(DATA_MARK in b for b in s.blocks): return 'listing_grid'
    if not body: return None
    if all(UI_TEXT.match(b) for b in body): return 'ui_chrome'
    if s.tag == 'pre' or all(b.startswith('```') for b in body): return 'code_example'
    if sum(1 for b in body if KV.match(b)) >= max(2, 0.7 * len(body)): return KV_FOR.get(ptype, 'spec_table')
    text = ' '.join(body)
    link_chars = sum(len(t) for t, _ in s.links)
    if len(text) >= 250 and link_chars < 0.25 * len(text) and not any(FACT.match(b) for b in body):
        return 'prose?'                            # prose for sure; which kind is asked (cheaply) below
    return None


def options(ptype):
    names = [c.name for c in BY_CATEGORY.get(ptype, [])] + GENERIC + [c.name for c in BY_CATEGORY['chrome']]
    return {n: BY_NAME[n].desc for n in dict.fromkeys(names)}


def label(segs, ptype, meta, judge):
    ask, prose = [], []
    for s in segs:
        r = _rule(s, ptype)
        if r == 'prose?':
            s.label, s.how = PROSE_FOR.get(ptype, 'article_body'), 'rule'
            prose.append(s)
        elif r:
            s.label, s.how = r, 'rule'
        else:
            ask.append(s)
    if judge and (ask or prose):
        crit, pcrit = options(ptype), {n: BY_NAME[n].desc for n in PROSE_KINDS}
        state = f"Web page ({ptype}): {meta.get('title', '')}\nURL: {meta.get('url', '')}"
        q = lambda s, c: {'type': 'choice', 'criteria': c, 'instructions': 'Which component is this section of the page?\nSection:\n' + s.text[:600]}
        qs = {f's{i}': q(s, crit) for i, s in enumerate(ask)}
        qs.update({f'p{i}': q(s, pcrit) for i, s in enumerate(prose)})
        a = judge.ask(state, qs)
        if a:
            for i, s in enumerate(prose):
                s.label, s.how, s.confidence = a[f'p{i}']['choice'], 'jev-prose', a[f'p{i}'].get('confidence', 0.0)
                if BY_NAME[s.label].shape == 'drop' and s.confidence < DROP_CONFIDENCE:
                    s.label, s.how = PROSE_FOR.get(ptype, 'article_body'), 'kept'
            for i, s in enumerate(ask):
                s.label, s.how, s.confidence = a[f's{i}']['choice'], 'jev', a[f's{i}'].get('confidence', 0.0)
                if BY_NAME[s.label].shape == 'drop' and s.confidence < DROP_CONFIDENCE:
                    s.label, s.how = PROSE_FOR.get(ptype, 'article_body'), f'kept (jev said {s.label} {s.confidence:.2f})'
    for s in ask:
        if not s.label:                            # no model: keep it, as generic content
            s.label, s.how = PROSE_FOR.get(ptype, 'article_body'), 'default'
    return segs


# ---------- filling + rendering ----------
ALIASES = {'name': ['name', 'headline', 'title'], 'headline': ['headline', 'name'], 'title': ['name', 'headline', 'title'],
           'price': ['offers.price', 'offers.lowPrice', 'price'], 'brand': ['brand.name', 'brand'],
           'rating': ['aggregateRating.ratingValue'], 'rating_count': ['aggregateRating.reviewCount', 'aggregateRating.ratingCount'],
           'author': ['author.name', 'author'], 'date': ['datePublished', 'startDate', 'uploadDate'],
           'availability': ['offers.availability'], 'standfirst': ['description'], 'description': ['description'],
           'time': ['totalTime'], 'servings': ['recipeYield'], 'venue': ['location.name'], 'channel': ['author.name'],
           'views': ['interactionStatistic.userInteractionCount'], 'followers': ['interactionStatistic.userInteractionCount']}


def ld_header(ld, ptype):
    """The page's main entity from JSON-LD, filled into its header component."""
    for o in main_entities(ld):
        types = _types(o)
        comp = next((BY_LD[t] for t in types if t in BY_LD and BY_LD[t].shape == 'header'), None)
        if not comp: continue
        flat = datatables.flatten(o)
        vals = {}
        for f in comp.fields:
            for k in ALIASES.get(f, [f]):
                v = flat.get(k)
                if v not in (None, '') and not str(v).startswith('http'):
                    vals[f] = re.sub(r'^https?://schema.org/', '', str(v)); break
        if vals.get('name') or vals.get('headline') or vals.get('title'):
            return comp, vals
    return None, {}


def render_header(comp, vals):
    title = vals.get('name') or vals.get('headline') or vals.get('title')
    facts = [f'**{k.replace("_", " ").title()}:** {v}' for k, v in vals.items() if k not in ('name', 'headline', 'title', 'description', 'standfirst')]
    out = [f'# {title}']
    if facts: out.append(' · '.join(facts))
    if vals.get('standfirst') or vals.get('description'): out.append(vals.get('standfirst') or vals.get('description'))
    return out


STEP_HEADING = re.compile(r'^#+ (step|stage|part)?\s*\d+\.?$', re.I)


def render_segment(s, comp, prev):
    """Blocks keep their page order; only the section's leading headings are treated as its title."""
    lead = 0
    while lead < len(s.blocks) and HEADING.match(s.blocks[lead]):
        lead += 1
    out, rest = list(s.blocks[:lead]), s.blocks[lead:]
    if not out and comp.heading and prev != comp.name:
        out.append(f'## {comp.heading}')
    if comp.shape == 'header':
        short = [b for b in rest if len(b) <= 80 and not HEADING.match(b)]
        out += ([' · '.join(re.sub(r'^- ', '', b) for b in short)] if short else []) + [b for b in rest if b not in short]
    elif comp.shape in ('bullets', 'links'):
        out += [b if b.startswith(('- ', '|', '```', '#')) else f'- {b}' for b in rest[:15 if comp.shape == 'links' else None]]
    elif comp.shape == 'steps':        # "step 1".."step 11" headings carry nothing once the steps are numbered
        out = [b for b in out if not STEP_HEADING.match(b)]
        items = [re.sub(r'^- ', '', b) for b in rest if not STEP_HEADING.match(b)]
        out += [b if HEADING.match(b) else f'{i}. {b}' for i, b in enumerate(items, 1)]
    else:                              # kv, prose, qa, table, code: the blocks already have the right form
        out += rest
    return out


# short facts that belong in the main header's facts line, keyed by the field they fill
FACT_FIELD = {'price_offer': 'Price', 'review_summary': 'Rating', 'stock_status': 'Availability', 'shipping_returns': 'Shipping',
              'variant_picker': 'Options', 'seller_info': 'Seller', 'result_count': 'Results', 'stat_highlight': 'Stats',
              'contact_info': 'Contact', 'opening_hours': 'Hours', 'genre_tags': 'Genres', 'breadcrumb': 'Category'}
NEAR = 8                          # how far from the header a fact may sit


def header_facts(segs):
    """Fill the main header component: index of the header section, and the nearby short fact sections that
    fill its fields (price, rating, availability...)."""
    h = next((i for i, s in enumerate(segs) if BY_NAME.get(s.label) and BY_NAME[s.label].shape == 'header'), None)
    if h is None: return None, {}
    facts = {}
    for i in range(max(0, h - NEAR), min(len(segs), h + NEAR + 1)):
        s = segs[i]
        if s.label in FACT_FIELD and len(s.text) <= 120:
            facts[i] = (FACT_FIELD[s.label], re.sub(r'^#+ ', '', s.text))
    return h, facts


def render(segs, ptype, meta, ld, cands):
    from .extract import DATA_MARK
    lines, prev, dropped = [], None, Counter()
    comp, vals = ld_header(ld, ptype)
    header_text = ''
    if comp:
        h = render_header(comp, vals)
        lines += h; header_text = ' '.join(h).lower(); prev = comp.name
    tables = [datatables.render([c]) for c in cands]
    h, facts = header_facts(segs)
    for i, s in enumerate(segs):
        c = BY_NAME.get(s.label) or BY_NAME[PROSE_FOR.get(ptype, 'article_body')]
        if c.shape == 'drop':
            dropped[c.name] += 1; continue
        if i in facts: continue                  # rendered inside the header's facts line
        if i == h and facts:
            block = render_segment(s, c, prev)
            by_field = {}
            for f, v in facts.values(): by_field.setdefault(f, []).append(v)
            block.insert(1 if block and HEADING.match(block[0]) else 0,
                         ' · '.join(f'**{f}:** ' + '; '.join(dict.fromkeys(v)) for f, v in by_field.items()))
            if comp and c.name == comp.name:
                block = [b for b in block if b.lower().lstrip('# ') not in header_text]
            lines += block; prev = c.name; continue
        if any(DATA_MARK in b for b in s.blocks) and tables:
            lines += tables.pop(0); prev = 'listing_grid'; continue
        block = render_segment(s, c, prev)
        if comp and c.name == comp.name:         # DOM copy of the JSON-LD header: keep only what it adds
            block = [b for b in block if b.lower().lstrip('# ') not in header_text]
        lines += block
        prev = c.name
    for t in tables:
        lines += t
    return lines, dropped


def signature(s):
    return hashlib.sha1(s.text[:200].encode()).hexdigest()[:12]
