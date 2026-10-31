# givememd component-classifier gold set

19 hand-labeled pages (611 sections, 78 fields) for evaluating the page -> sections -> component pipeline.
Each label was assigned by reading the cached page itself, using only the catalog in `givememd/components.py`
(CATEGORIES + CATALOG names and descriptions). It is **independent of the system under test**: we did not read or run
the segmenter/classifier/renderer (`segment.py`, `classify.py`, `render.py`, `decide.py`, `extract.py`, `jev.py`), did not
call the TypeSafe/Jev API, and did not use earlier eval keys or outputs. Nothing was fetched; the inputs are the cached
raw HTML of each page as fetched on 2026-10-30 (`python bench/fetch_pages.py` rebuilds a cache; pages may have changed since).

## File format
```json
{"page": "amazon", "url": "...", "page_type": "<CATEGORIES key, never chrome>",
 "sections": [{"text": "<exact visible-text snippet>", "component": "<catalog name>", "note": "...", "alt": ["..."]}],
 "fields": {"<component>.<field>": "<exact visible value>"}}
```
- `sections` are in top-to-bottom DOM order.
- `alt` is an **extension to the requested schema**. It is optional and appears on 180 of 611 sections, listing other components a careful
  human would also accept. `component` is always the single best call. A strict scorer uses `component` only; a lenient scorer
  also accepts `alt`. Report both scores. The gap between them measures how much of the error is genuine catalog ambiguity.
- `note` is optional and explains a judgment call.

## How labels were made
1. The visible text for each page was extracted with selectolax (Lexbor). Start from `<body>`, strip
   `script, style, noscript, template, svg`, take `body.text(separator=' ')`, and collapse whitespace (`re.sub(r'\s+', ' ', s).strip()`).
   A per-block dump with DOM tag paths was used to judge section boundaries and spot hidden or duplicated blocks.
2. Each page was read top to bottom. Every distinct content section got at least one snippet. Representative chrome
   (navigation, footer, promos, login prompts, UI text, recommendations) was also labeled.
   For repeated items (reviews, cards, replies), 2–5 representatives were labeled individually.
3. Labels follow "what the section IS for a reader", using the catalog descriptions. Shared conventions:
   - Text before the first subheading is `article_body` in articles, `doc_prose` in docs and `encyclopedia_section` in reference pages.
   - Article text under a subheading is `subheading_section`, with alt `article_body`.
   - A docs title plus intro is `doc_header`.
   - The main buy-box price is `product_header`. Secondary or used offers are `price_offer`. Card, member and upsell offers are `promo_ad`.
     Snippets were chosen so that each one contains only one of these.
   - Listing-page cards are `real_estate_listing` or `event_card`, with alt `listing_card`.
4. Fields: 3–8 key fields for the main header-type component, using values exactly as they appear on the page. On listing pages,
   the fields describe the **first** card.

## Snippet verification rule (all 611 snippets and all 78 field values pass)
- `text` is 15–80 characters, already whitespace-collapsed, and occurs in the whitespace-collapsed visible text defined above.
- No snippet is repeated within a file, and snippets are in order of first occurrence.
- Every field value occurs in the same visible text. Every component name is in CATALOG, and `page_type` is a CATEGORIES key other than `chrome`.
- Soft warnings (allowed, 121 total: 80 node-spanning, 34 repeated, 6 wikipedia field keys, 1 zillow section count):
  - (a) 80 snippets **span several DOM text nodes**. They match `text(separator=' ')` but not `text(separator='')`.
    Examples are syntax-highlighted code ("const [ state , setState ] = useState ( initialState )"), link lists with no spaces between links,
    and multi-span ratings. An evaluator must locate snippets in the space-separated form.
  - (b) 34 snippets **occur more than once**, because the site renders the block twice: mobile and desktop copies
    (allbirds, github About, pydocs sidebar), duplicated carousels (eventbrite, up to 4x), lightbox captions (guardian, ars),
    or the react sandbox toolbar (5x). All copies have the same role, so locate by **first occurrence**.
  - (c) The wikipedia field keys use the form `infobox.facts.<label>`; see below.
- The rule above is complete enough to reimplement it.

## Per-page counts
"Content" excludes the chrome category, which here also includes `recommendations`.

| page | page_type | sections | content | chrome | with alt | fields |
|---|---|---|---|---|---|---|
| airbnb | listings | 17 | 5 | 12 | 2 | 0 |
| allbirds | commerce | 40 | 24 | 16 | 13 | 4 |
| amazon | commerce | 45 | 29 | 16 | 8 | 7 |
| ars | article | 22 | 15 | 7 | 5 | 4 |
| blog | article | 29 | 23 | 6 | 15 | 4 |
| eventbrite | listings | 25 | 14 | 11 | 13 | 3 |
| forum | community | 25 | 21 | 4 | 4 | 4 |
| github | docs | 45 | 36 | 9 | 18 | 6 |
| goodreads | media | 30 | 21 | 9 | 12 | 5 |
| guardian | article | 29 | 19 | 10 | 4 | 4 |
| ikea_pdp | commerce | 45 | 27 | 18 | 15 | 6 |
| linkedin | profile | 23 | 9 | 14 | 8 | 5 |
| mdn | docs | 44 | 33 | 11 | 8 | 2 |
| nike_pdp | commerce | 26 | 15 | 11 | 10 | 3 |
| pydocs | docs | 45 | 41 | 4 | 15 | 2 |
| react | docs | 39 | 30 | 9 | 4 | 3 |
| recipe | food_health | 30 | 15 | 15 | 9 | 4 |
| wikipedia | reference | 39 | 27 | 12 | 8 | 6 |
| zillow | listings | 13 | 12 | 1 | 9 | 6 |
| **total** | | **611** | **416** | **195** | **180** | **78** |

74 of 121 catalog components are used. The most common are doc_prose 60, navigation 56, footer 53, ui_chrome 34, code_example 21,
article_body 20, encyclopedia_section 15, promo_ad 14, login_prompt 14 and subheading_section 14.
These components are never used, because none of the 19 pages has them: media/travel/finance headers, listing_grid, listing_card (alt only),
key_takeaways, social_post, profile_header, hero, pricing_plans, stat_highlight, compat_table (alt only) and others.

## Known gaps and departures from the spec
- **zillow (13) and airbnb (17)**: the cached HTML is skeletal (about 1.3k characters each). Zillow has 9 home cards. Airbnb has **no listings
  at all**: "Fake title 1..10" are skeleton placeholders (`ui_chrome`), and the file has no fields. No sections were invented to reach 15.
- **linkedin**: the cached page is a VC fund that is also called "Anthropic" (2–10 employees, founded 2012), not the AI lab. It is labeled as served.
- **mdn and pydocs have only 2 fields**, because `doc_header` defines only title and summary. For react, `api_signature.signature` was added as a third field.
- **wikipedia** has no header-type component. Its fields are infobox facts, keyed `infobox.facts.<label>` (for example
  `infobox.facts.Developed by: John Gruber`), because the catalog field is the single `facts`.
- **pydocs** (about 60k characters, about 60 API entries) is sampled with 45 sections, not exhaustively covered.
- **Empty widgets in the cached HTML**:
  - allbirds and nike reviews, github Languages/Releases/Contributors and the guardian "Most viewed" titles are not present. These are either
    unlabeled or labeled `ui_chrome`/`review_summary` (nike "No Reviews").
  - amazon has no individual reviews, only the AI "Customers say" summary and topics (`review_summary`), plus "Sign in to see customer reviews" (`login_prompt`).
- **Not labeled because no 15-character snippet works**: the ars kicker "Is that a lot?", the guardian byline "Richard Cooke" (kept as a field only),
  forum like counts, and zillow "More Showcase Save".
- Hidden-but-in-DOM text (closed modals, one-tap login, hidden dropdowns) is in "visible text" by the stated definition. When it
  was labeled, it got its role label, for example the allbirds policy modals as `shipping_returns`/`footer`.

## Ambiguous calls (component chosen, with alt)
- **Commerce**
  - amazon: the main price string also appears earlier in "Other sellers … from $180.90". The `product_header` price snippet is therefore
    "bought in past month $180.90", and the adjacent Visa "$50 Amazon Gift Card" is `promo_ad`. The buy box is a *used* offer, so it is
    labeled `price_offer` + `seller_info`, not `product_header`.
  - amazon: the "Customers say" topic summaries and per-topic excerpts are `review_summary` (alt `review_item`).
  - Member pricing is `price_offer` (alt `promo_ad`): IKEA Family "$65.00", the Low Price Guarantee, and nike "excluded from promotions".
  - Feature blurbs on nike and allbirds are split between `feature_bullets` and `feature_grid` (each has the other as alt).
  - ikea "WARNING! Tipping hazard" and the "Good to know" note are `callout_note` (a docs component on a product page).
- **Articles and community**
  - blog reader comments are labeled `comment_list` each, because the catalog has no per-comment component.
  - Comment areas that are only a sign-in prompt or "Loading comments…" are `login_prompt`/`ui_chrome` (alt `comment_list`).
  - guardian end note about the author's book is `article_body` (alt `author_bio`, `promo_ad`). The bookshop line is `promo_ad`. The inline
    "Read more" card is `related_articles`.
  - forum: a quote of the OP inside a reply is `answer` (alt `pull_quote`), and a code block in a reply is `code_example` (alt `answer`).
    The OP author/date line is `thread_header` (alt `post_body`).
- **Profile and listings**
  - linkedin "About us" prose is `org_header` (alt `article_body`), since there is no org-description component.
  - Listing-page h1s are `result_count`: zillow "Austin TX Real Estate & Homes For Sale" and eventbrite.
  - The eventbrite city-guide intro prose is `article_body` (alt `encyclopedia_section`), and its promoted card is `promo_ad` (alt `event_card`).
- **Recipe and book**
  - recipe: the same "4.5 out of 5. 526 ratings" text is `recipe` at the top and `review_summary` at the bottom. goodreads has the same
    pattern (`book_header` vs "Community Reviews").
  - recipe: diet tags are `genre_tags`; "Recipe from Good Food magazine, September 2017" is `citations`; the serving tip is `callout_note`.
  - goodreads: the blurb is `product_description` (alt `article_body`). "Alternate covers of this ISBN…" is `correction_note`.
- **Docs and reference**
  - pydocs: "Changed in version 3.12" is `changelog_entry` (alt `callout_note`). Prose describing arguments is `parameter_list` (alt `doc_prose`).
    "Return …" method text is `return_value`. "See also" boxes are `see_also`.
  - react: Caveats bullet lists are `doc_prose` (alt `callout_note`). Deep Dive boxes are `callout_note`. Troubleshooting Q&A is `doc_prose`.
  - wikipedia: the short description "Plain text markup language" is `definition`. The maintenance banner is `correction_note`.
    The examples table (source/HTML/rendered) is `code_example` (alt `data_table`). Further reading is `citations`, and External links are `see_also`.
  - github: topics are `genre_tags`. The contribution in/out-of-scope lists are `community_rules`. The backend comparison table is `product_comparison`.

## Components we wished existed
- comment_item (a single comment)
- org_about / org description
- encyclopedia_header (title + short description)
- book/media description
- edition_details
- version_note (added/changed/deprecated)
- api_entry (signature + description + params)
- caveats
- troubleshooting
- topic_tags (a generic tag list; genre_tags sits under media)
- external_links
- maintenance_banner
- contributing_guidelines
- legal_text / policy_document
- care_instructions
- safety_warning
- documents_downloads
- loyalty / member_offer
- buy_box / purchase_actions
- brand_badges
- back_in_stock_signup
- recipe_tags / diet badges
- source_credit / attribution
- listing page title / intro
- quoted_reply
- Field gaps: `doc_header.last_updated`, `recipe.author`, `recipe.description`, `org_header.description`, `book_header.description`.

## Appendix: per-page labeling notes (verbatim)

### airbnb (search results Austin; cached HTML is a skeleton, no listings rendered)
- 17 sections, all chrome except result_count; zero real listings exist in the HTML.
- "Fake title 1..10" skeleton placeholders -> ui_chrome (they sit where filter/category chips render).
- "It's easy to start hosting and earn extra income." (Become a host menu) -> promo_ad; alt login_prompt.
- "Search results; Over 1,000 stays" (visually hidden h1) -> result_count.
- fields: {} — no header-type component on the page. Could not label any listing content because none exists.
- Many snippets span several tiny nodes (nav tabs, buttons) -> fail the unseparated-text check; unavoidable at >=15 chars.

### allbirds (40 sections, 4 fields)
- Product info is rendered twice (mobile md:hidden + desktop); several snippets occur 2x (Final Sale text 4x). Labels identical for both copies.
- product_header snippet uses desktop copy "Image Men's Tree Runner Also available in: Women's Sizes $100" (leading "Image" from gallery button, needed for uniqueness).
- Reviews widget is empty (JS-loaded): "Reviews for Men's Tree Runner" -> ui_chrome (alt review_summary). No review content to label.
- Closed footer modals carry ~90k chars: Refund policy & Shipping policy -> shipping_returns (alt footer); Privacy policy & Terms -> footer (no legal_text component).
- Brand-mission banner "Better Things in a Better Way" -> promo_ad (alt hero); value-prop tiles above footer -> feature_grid (alt promo_ad); BREATHABLE/LIGHTWEIGHT callouts -> feature_grid (alt feature_bullets).
- "Notify me when back in stock" email form -> newsletter_signup (alt login_prompt). Care instructions -> product_description (alt spec_table).
- Wished: care_instructions, legal_text/policy_document, back_in_stock_signup.

### amazon (45 sections, 7 fields)
- Main price "$180.90 $ 180 . 90" also occurs earlier in the Other-sellers offer; product_header price snippet is "bought in past month $180.90" (includes adjacent social-proof text). Isolated Visa promo "Get a $50 Amazon Gift Card..." = promo_ad.
- Buy box is the USED offer (Buy Used: $180.90, Condition: Used: Acceptable, Sold by Amazon Resale) -> price_offer / seller_info, not product_header.
- "Customers say" AI summary + topic chips + per-topic review excerpts all -> review_summary (alt review_item for excerpt drilldowns). No full review_item exists in HTML ("Sign in to see customer reviews" = login_prompt).
- "Top Brand: Apple / Highly Rated / Low Returns" badges -> seller_info (alt promo_ad); "There is a newer version of this item" -> recommendations (alt promo_ad).
- Manufacturer "Technical Details" (controls, compatibility, sensors) -> spec_table; its "In the Box" row -> whats_in_box (alt spec_table); device compatibility -> spec_table (alt compat_table).
- "Add to cart / Add to List" buttons, compatibility-checker widget, "How customer reviews work" help -> ui_chrome.
- Wished: buy_box/purchase_actions; brand_badges.

### ars
- Kicker "Is that a lot?" (14 chars) dropped: too short for a snippet; it belongs to article_header.
- Caption "Did an AI agent order that DoorDash basket? …" occurs 2x (hidden lightbox + visible figure); typo "certianly" is on the page.
- Text-settings dropdown (size/width/theme) -> ui_chrome. Wished: `reader_settings` (not needed, ui_chrome fits).
- Comments: only "7 Comments … Loading comments..." placeholder -> ui_chrome (alt comment_list).
- "Most Read" numbered list -> related_articles.
- Paragraphs after subheading "Give it time?" -> subheading_section (alt article_body).
- "Ars Technica has been separating the signal from the noise…" site blurb -> footer.

### blog
- Substack top bar "One Useful Thing Subscribe Sign in" -> navigation (alt login_prompt).
- Subtitle "From the Hugging Face Incident to Twilight Factories" -> article_header (standfirst).
- Paragraphs under "The Hugging Face Incident" / "The Twilight Factory" -> subheading_section (alt article_body); intro paragraphs -> article_body.
- Engagement bar "1,064 163 113 Share Previous Next" -> share_buttons (counts are likes/comments/restacks).
- Comments: individual reader comments labeled comment_list (no per-comment component in catalog; answer/social_post don't fit). Wished: `comment_item`.
- "23 replies by Ethan Mollick and others 161 more comments..." -> ui_chrome (alt comment_list).
- "Top Latest Discussions No posts" -> ui_chrome, empty related-posts widget (alt related_articles).
- "Ready for more? Subscribe" -> newsletter_signup. "Start your Substack Get the app" -> footer (alt login_prompt).

### eventbrite (Austin events discovery page)
- Every carousel is rendered twice in DOM, and some cards recur across carousels -> card snippets occur 2-4x; all copies carry the same label, first occurrence is the one meant.
- Intro city-guide prose under h1 "Best events in Austin" -> article_body; alt encyclopedia_section. Wish: listing/category intro text component.
- Promoted card ("From $0.00 MLOps World 1.5k followers Promoted") -> promo_ad (sponsored item); alt event_card.
- Cards -> event_card, alt listing_card (per shared convention). "Almost full"/"Going fast" badges treated as part of card, not stock_status.
- "Points of Interest near Austin ..." SEO link list -> navigation; alt recommendations.
- FAQ question and answer snippets -> faq.
- Fields are for the FIRST card (Haunted Rooftop); no price is shown ("Check ticket price on event"), so no event_card.price.

### forum (discuss.python.org, crawler/noscript render, 10 posts)
- OP meta line "October 27..." -> thread_header (author/date of the thread); alt post_body.
- OP inline bold subheadings ("Rehoming bench_runner...", "A perf bot") kept inside post_body, not subheading_section.
- Quoted OP text at top of a reply ("Workloads: ...") -> answer (it is part of the reply); alt pull_quote.
- Code block inside reply #8 -> code_example; alt answer.
- thread_header.votes = "20 Likes" (OP like count; no vote count exists). No reply count/views visible, so no answers/views fields.
- Like counts ("2 Likes") not labeled: too short to snippet in isolation.
- Wish: quoted_reply (quote of an earlier post inside a reply).

### github (microsoft/markitdown) — 45 sections, 6 fields
- About sidebar is duplicated in DOM (NarrowOnly copy near top, desktop copy after README); snippets "Python tool for converting..." etc. occur 2x. Labeled at first occurrence.
- Description -> repo_header; stats "Watchers 588 watching" -> repo_header (spans nodes; not in unseparated text).
- Topics (autogen-extension ...) -> genre_tags; alt repo_header, skills_list. Wished: generic `tag_list` (genre_tags is filed under media).
- README title + intro para -> doc_header (alt doc_prose). Fields carry both repo_header and doc_header.
- Supported-format list -> feature_bullets (commerce component on a docs page); alt doc_prose.
- pip extras list "[xls] Installs dependencies for older Excel files" -> parameter_list; alt install_instructions/doc_prose. Wished: `option_list`/extras.
- Built-in vs Doc Intelligence vs Content Understanding table -> product_comparison; alt data_table.
- "Cost note:" bold paragraph -> callout_note (no box); alt doc_prose.
- What to Contribute in/out of scope lists -> community_rules; alt doc_prose. Wished: `contributing_guidelines`.
- Trademarks legal paragraph inside README -> doc_prose; alt footer.
- Docker commands -> install_instructions; alt cli_reference/code_example.
- repo_header.language not visible (Languages widget empty in cached HTML); Releases/Used by/Contributors/Languages headings are empty widgets — not labeled.

### goodreads (The Great Gatsby)
- page_type media (book page); main header = book_header.
- Book blurb ("The only edition of the beloved classic...") -> product_description; no book/media description component and book_header has no description field. alt article_body.
- "Alternate covers of this ISBN can be found here" -> correction_note (librarian/editor note prefixed to the blurb); alt product_description.
- "180 pages, Paperback" / "First published April 10, 1925" -> book_header (details facts line under the blurb, physically separated from the title block); alt spec_table.
- About the author block (stats + long bio) -> author_bio; stats line alt profile_header. The bio is a full Wikipedia-style biography, larger than a typical byline bio.
- Header "3.92 6,176,808 ratings" -> book_header; identical numbers under "Community Reviews" + histogram -> review_summary.
- "Search review text" -> search_box (alt filter_panel); "Displaying 1 - 30 of 140,503 reviews" -> result_count; "More reviews and ratings" -> pagination.
- "Join the discussion 1,330 quotes 850 discussions 116 questions" -> navigation (links to sub-pages with counts); alt related_articles / stat_highlight.
- Per-review star ratings are not in visible text (icons/aria only), so review_item rating cannot be checked from text.
- Several snippets (header rating, histogram, result count) span DOM nodes; they pass the space-separated check but not the unseparated one — unavoidable, nodes are <15 chars.
- Wish: book_description (or media description field), quotes/discussion stats block, edition_details (format/pages/ISBN/published) component.

### guardian
- Byline only "Richard Cooke" (13 chars) -> no section snippet; given as field only. Headline snippet truncated (full headline > 80 chars).
- Inline rich link "‘People thought I was a communist…’ is Wikipedia’s Jimmy Wales the last decent tech baron?" -> related_articles (inline read-more card inside body).
- Book end note "The Last Best Place on the Internet … is out now through Black Inc" -> article_body (alt author_bio, promo_ad); next line "order your copy … guardianbookshop.com" -> promo_ad.
- Blockquote aside "Gaytha Langlois, wrote about two things dear to her" -> pull_quote.
- Top bar "Print subscriptions Newsletters Sign in US edition…" -> navigation (alt login_prompt).
- Comments area only shows "Sign in or create your Guardian account to join the discussion" -> login_prompt (alt comment_list).
- "Explore more on these topics …" tag links -> navigation (alt genre_tags). Wished: `topic_tags` for article tags.
- "Most viewed" block contains only tab labels (no story titles in cached HTML) -> not labeled as related_articles.
- No subheadings in the article, so all body paragraphs = article_body.
- Main image caption appears twice (lightbox + figure).

### ikea_pdp (45 sections, 6 fields)
- IKEA Family member price "In-store only price $65.00 ... Offer valid ..." -> price_offer (alt promo_ad); main price "$ 79.00" -> product_header. "Collect 79 points with IKEA Family" -> promo_ad. Low Price Guarantee -> price_offer (alt promo_ad, shipping_returns).
- Tab bar (Overview / Product details / Measurements / FAQ) -> table_of_contents (alt navigation).
- "Good to know" note & "WARNING! Tipping hazard" -> callout_note (docs component used on commerce page); wished safety_warning.
- "Assembly and documents" PDF links -> navigation (wished documents/downloads component).
- Reviews appear twice: full SEO list (title, author, text, stars) and a "Customer reviews" summary + 3-card highlight carousel; both lists -> review_item; "Customer reviews" heading (with 4.5 / 2117) -> review_summary.
- AI-generated FAQ disclaimer -> faq (alt ui_chrome). Empty "As seen on Instagram" gallery -> ui_chrome.
- Materials/care and Assembly blocks rendered twice -> 2x warnings.
- Wished: documents_downloads, safety_warning, loyalty_offer (member pricing sits between price_offer and promo_ad).

### linkedin (guest view of linkedin.com/company/anthropic)
- NB: the page is a VC fund also named "Anthropic" (2-10 employees, founded 2012), not the AI lab. Labels/fields reflect the page as served.
- "About us" description prose -> org_header (company description belongs to the org card); alt article_body. Wish: org_about / description prose component (profile category has no long-form "about" component; profile_header has a bio field but org_header does not).
- About kv facts (Website, Industry, Company size, Type, Founded) -> org_header; Website alt contact_info.
- "Discover all 19 employees" -> org_header (top-card stat link); alt people_list.
- "Similar pages" company list -> recommendations (no "related profiles" component).
- "Browse jobs" / "More searches" SEO job-category link lists -> navigation; alt recommendations.
- "Agree & Join LinkedIn" is inside a hidden Google one-tap module; "Report this company" in a hidden dropdown — both still in body text, labeled login_prompt / ui_chrome.
- No headquarters shown, so no org_header.headquarters field.

### mdn (Using the Fetch API) — 44 sections, 2 fields
- Only 2 fields: doc_header has only title/summary in catalog; no other header component applies. Wished: doc_header.last_updated ("This page was last modified on Aug 20, 2025").
- First intro sentence -> doc_header; remaining intro paras (before first H2) -> doc_prose.
- Option-value lists (credentials omit/same-origin/include; Response.type basic/cors/opaque) -> parameter_list; alt doc_prose, definition.
- CSRF caution is plain prose, not a box -> doc_prose; alt callout_note. No Note/Warning boxes on this page.
- "Check out the video course from Scrimba, our partner" (inside Learn mega-menu) -> promo_ad.
- "Help improve MDN" -> ui_chrome (alt call_to_action); last-modified line -> footer (alt doc_header).
- Left sidebar (Fetch API guides/interfaces) is in DOM after the article -> navigation, labeled at its DOM position.

### nike_pdp (26 sections, 3 fields)
- No size/color picker in cached HTML; "Shown: <colorway> Style: IU4686-002" -> spec_table (alt variant_picker).
- "This product is excluded from site promotions and discounts." -> price_offer (alt promo_ad).
- Titled feature blurbs (Responsive Air Zoom Unit, Stable Flyplate...) -> feature_bullets (alt feature_grid, product_description); "What's New?" list -> feature_bullets (alt key_takeaways).
- Reviews accordion with 0 reviews ("No Reviews ... Write a Review") -> review_summary (alt ui_chrome).
- Product details panel repeats title + $280 ("View Product Details" modal content); labeled its prose only.
- Nav/footer link lists have no whitespace between links in unseparated text; several multi-link snippets only match the space-separated text. Footer rendered twice -> 2x warnings.
- product_header.brand "Nike" taken from the title "Nike Alphafly 4" (no separate brand line).

### pydocs (pathlib) — 45 sections, 2 fields
- Sphinx sidebar/related bars are duplicated (mobile menu at top, desktop sidebar at bottom): TOC, prev/next, breadcrumb snippets occur 2x; "Theme Auto Light Dark" 3x.
- API signature snippets ("class pathlib. PurePath ( * pathsegments )") are built from many spans; they match the space-separated text only.
- "Changed in version 3.12: The walk_up parameter was added" -> changelog_entry; alt callout_note. Deprecation note -> callout_note; alt changelog_entry. Wished: `version_note` (added/changed/deprecated in version X).
- No formal parameter lists on this page; parameter prose ("If parents is true...", "Each element of pathsegments...") -> parameter_list; alt doc_prose. Judgment call.
- Method descriptions starting "Return ..." -> return_value; alt doc_prose. Property description (parts) -> doc_prose; alt return_value.
- "See also" admonition boxes -> see_also; alt callout_note.
- Pattern language wildcard list -> definition; alt data_table/doc_prose. Wished: `glossary`/definition_list.
- Corresponding tools table (os vs pathlib) -> data_table; alt product_comparison. Footnotes -> citations.
- Wished: `api_entry` (signature + description + params as one unit) — the page is ~60 short API entries; per-paragraph labels are a judgment call.
- Only 2 fields (doc_header title/summary); page is long (60k chars), so 45 sections sample it rather than cover every API entry.

### react
- Caveats lists (useState + set function) -> doc_prose (alt callout_note): they are bulleted caveats, not boxed notes. Wished: `caveats` / `limitations` list component.
- "Deep Dive" collapsible -> callout_note (alt doc_prose).
- Example tab switcher ("1 . Counter (number) 2 . Text field ...") -> navigation (alt ui_chrome).
- Troubleshooting entries (question heading + answer prose) -> doc_prose; could be read as faq. Wished: `troubleshooting` (problem/solution) component.
- Inline TOC under intro -> table_of_contents (same list repeats in "On this page"; snippet occurs 2x, first = inline TOC).
- "API Reference Hooks" -> breadcrumb.
- Code is syntax-highlighted per token: code snippets only match the space-separated text form (e.g. "const [ state , setState ] = useState ( initialState )"), not the unseparated form.
- doc_header has only title/summary fields; added api_signature.signature as 3rd field.
- Sandbox toolbar "App.js App.js Reload Clear Fork" repeats 5x (all ui_chrome).
- Not labeled: "Copy page" button (too short), second api_signature heading "set functions, like setSomething(nextState)" (only appears as a heading repeated 3x).

### recipe (bbcgoodfood easy chocolate cake)
- "Master the chocolate cake with an airy, light sponge..." -> recipe (standfirst inside the recipe header; recipe has no description field). alt article_body.
- "A star rating of 4.5 out of 5. 526 ratings Rate loading..." (top) -> recipe (header rating); bottom "Overall rating ..." -> review_summary. Same text, different role.
- "Freezable (sponges only)" / "Vegetarian" diet tags -> genre_tags (closest "tags"); alt recipe.
- "Pair chocolate cake with a few healthier dubai chocolate bites..." -> callout_note (editorial serving tip that links another recipe); alt article_body / recommendations.
- "Try these next-level, indulgent chocolate cake ideas from our sister title" -> related_articles; alt recommendations / promo_ad (cross-site promo).
- "Recipe from Good Food magazine, September 2017" -> citations (source credit); no attribution/provenance component.
- Comment section has only a rating/comment form, no comments -> ui_chrome (not comment_list).
- "Keep the screen awake with cook mode on the Good Food app." -> login_prompt (app download prompt).
- Wish: recipe_tags/diet_badges (vegetarian, freezable, difficulty); source_credit/attribution; recipe_intro (description) or a description field on recipe.
- Fields: author "Miriam Nice" is visible but recipe has no author field; omitted.

### wikipedia (Markdown article) — 39 sections, 6 fields
- No header-type component for an encyclopedia article (title + short description). Fields given as `infobox.facts.<label>` (catalog field is just `facts`); verify warns on these keys by design.
- "Plain text markup language" (short description under title) -> definition; alt encyclopedia_section. Wished: `encyclopedia_header` / `topic_header` (title, short description).
- Lead paragraphs (before first H2) -> encyclopedia_section (not article_body), per reference convention.
- Hatnote "For the marketing term, see Price markdown" -> disambiguation; alt navigation.
- Maintenance banner "relies excessively on references to primary sources" -> correction_note; alt ui_chrome. Wished: `maintenance_banner`/editorial-quality notice.
- Examples table (markdown source / HTML / rendered, 3 columns) -> code_example; alt data_table.
- Markdown Extra feature bullet list -> encyclopedia_section (list inside section).
- Further reading -> citations (alt see_also); External links -> see_also (alt citations, navigation). Wished: `external_links`.
- Navboxes, authority control, categories -> navigation.
- "Donate Create account Log in Personal tools" -> login_prompt; alt navigation.
- Hidden categories (display:none in real page) not labeled.

### zillow (search results, Austin TX; small cached render ~1.3k chars)
- Only 13 sections possible without inventing; page has 9 home cards + search/filter chrome.
- h1 "Austin TX Real Estate & Homes For Sale" -> result_count (results header); alt listing_grid. Wish: listing_page_title / results header.
- Home cards -> real_estate_listing, alt listing_card. Card fields are separate tiny nodes ("$449,000", "4", "bds"), so snippets use the address and broker lines.
- Open-house badge "Open: Tue 11am-12pm (11/10)" labeled real_estate_listing (part of card).
- "More Showcase Save" and "Loading..." not labeled: non-unique / too short.
- Fields are for the FIRST card (8709 Blaze Dr).
