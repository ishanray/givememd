"""Component catalog: every section of a web page is matched to one of these, filled, and rendered.

Each component has a category (first-stage choice), a short description (the decision model's criterion),
a shape (how it is filled from the DOM and rendered), the fields it carries, and the JSON-LD types that can
fill it directly. Shapes:

  header   title + one line of facts          kv       key: value pairs
  bullets  list of short items                prose    paragraphs
  steps    numbered list                      qa       question / answer pairs
  table    rows and columns                   cards    repeated items -> one table
  code     code with surrounding text         links    titled links (rendered only if asked)
  drop     not content; never rendered
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Component:
    name: str
    category: str
    desc: str
    shape: str
    fields: tuple = ()
    ld: tuple = ()               # JSON-LD @types that fill this component
    heading: str = ''            # section heading when rendered ('' = the section's own heading)


def C(name, category, desc, shape, fields='', ld='', heading=''):
    return Component(name, category, desc, shape, tuple(fields.split()), tuple(ld.split()), heading)


CATEGORIES = {
    'commerce': 'a product for sale: its name, price, options, specs, shipping, reviews',
    'listings': 'many items listed together: search results, category pages, homes, jobs, events, people',
    'article': 'news, blog, essay or story content: headline, byline, body text, quotes, images',
    'docs': 'technical documentation, API references, code, tutorials, changelogs',
    'community': 'forum threads, questions and answers, comments, social posts',
    'profile': 'a person, company, place or channel: name, bio, stats, contact',
    'media': 'video, podcast, music, film, book or game details',
    'events_travel': 'events, tickets, hotels, flights, rentals, itineraries',
    'food_health': 'recipes, nutrition, menus, medical or fitness information',
    'data_finance': 'tables, statistics, prices, charts, financial quotes, comparisons',
    'business': 'company marketing: features, pricing plans, testimonials, FAQs, calls to action',
    'reference': 'encyclopedia or knowledge content: infobox, definitions, timelines, citations',
    'chrome': 'not content: navigation, footers, ads, cookie banners, login prompts, UI text',
}

CATALOG = [
    # ---- commerce
    C('product_header', 'commerce', 'main product name, brand, price, rating', 'header', 'name brand price list_price rating rating_count availability', 'Product'),
    C('price_offer', 'commerce', 'price, discount, sellers, deal or offer details', 'kv', 'price list_price discount seller condition', 'Offer AggregateOffer'),
    C('variant_picker', 'commerce', 'color, size, style or configuration options', 'bullets', 'option values', heading='Options'),
    C('spec_table', 'commerce', 'product specifications as key/value pairs', 'kv', 'specs', heading='Specs'),
    C('feature_bullets', 'commerce', 'bullet list of product features or highlights', 'bullets', 'items', heading='Features'),
    C('product_description', 'commerce', 'paragraphs describing the product', 'prose', 'text', heading='Description'),
    C('whats_in_box', 'commerce', "list of what's included in the box", 'bullets', 'items', heading="What's in the box"),
    C('shipping_returns', 'commerce', 'delivery, shipping, returns or warranty terms', 'kv', 'shipping returns warranty', heading='Shipping & returns'),
    C('stock_status', 'commerce', 'in stock, sold out, quantity left, bought recently', 'kv', 'availability'),
    C('review_summary', 'commerce', 'average rating, rating histogram, review topics', 'kv', 'rating count distribution topics', 'AggregateRating', 'Reviews'),
    C('review_item', 'commerce', 'one customer review: author, stars, date, text', 'prose', 'author rating date title text', 'Review', 'Review'),
    C('size_guide', 'commerce', 'size chart or fit guidance', 'table', 'rows', heading='Size guide'),
    C('product_comparison', 'commerce', 'table comparing several products side by side', 'table', 'rows', heading='Comparison'),
    C('bundle_offer', 'commerce', 'frequently bought together or bundle deal', 'links', 'items'),
    C('seller_info', 'commerce', 'seller or store name, ratings, policies', 'kv', 'name rating', 'Store', 'Seller'),
    # ---- listings
    C('listing_grid', 'listings', 'grid or list of many products, homes, results', 'cards', 'items', 'ItemList', 'Results'),
    C('listing_card', 'listings', 'one item in a listing: title, price, key facts', 'kv', 'title price facts'),
    C('result_count', 'listings', 'number of results, sort order, page info', 'kv', 'count sort'),
    C('filter_panel', 'listings', 'search filters and facets', 'drop'),
    C('pagination', 'listings', 'page numbers, next/previous links', 'drop'),
    C('real_estate_listing', 'listings', 'one home or rental: price, beds, baths, area, address', 'kv', 'address price beds baths area status', 'SingleFamilyResidence Apartment House Residence RealEstateListing'),
    C('job_posting', 'listings', 'job title, company, location, salary, description', 'kv', 'title company location salary type posted', 'JobPosting'),
    C('search_box', 'listings', 'search input and suggestions', 'drop'),
    C('map_widget', 'listings', 'map with pins or location picker', 'drop'),
    # ---- article
    C('article_header', 'article', 'headline, byline, date, standfirst of an article', 'header', 'headline author date standfirst', 'NewsArticle Article BlogPosting Report'),
    C('article_body', 'article', 'paragraphs of article or blog text', 'prose', 'text'),
    C('subheading_section', 'article', 'subheading followed by its paragraphs', 'prose', 'text'),
    C('pull_quote', 'article', 'highlighted quotation from the article', 'prose', 'text'),
    C('image_caption', 'article', 'caption or credit for a photo or figure', 'prose', 'text'),
    C('author_bio', 'article', 'short biography of the author', 'prose', 'text', heading='About the author'),
    C('key_takeaways', 'article', 'summary bullets, TL;DR, key points', 'bullets', 'items', heading='Key points'),
    C('table_of_contents', 'article', 'list of sections in this page', 'drop'),
    C('related_articles', 'article', 'links to other stories: most viewed, read next, related', 'links', 'items'),
    C('newsletter_signup', 'article', 'subscribe to a newsletter prompt', 'drop'),
    C('correction_note', 'article', 'correction, update or editor note', 'prose', 'text'),
    C('live_blog_entry', 'article', 'timestamped live blog update', 'prose', 'time text', 'LiveBlogPosting'),
    C('embedded_post', 'article', 'embedded social media post inside an article', 'prose', 'author text'),
    # ---- docs
    C('doc_header', 'docs', 'title and summary of a documentation page', 'header', 'title summary', 'TechArticle'),
    C('api_signature', 'docs', 'function, method or endpoint signature', 'code', 'signature'),
    C('parameter_list', 'docs', 'parameters or arguments with descriptions', 'kv', 'params', heading='Parameters'),
    C('return_value', 'docs', 'what a function returns', 'prose', 'text', heading='Returns'),
    C('code_example', 'docs', 'code snippet, possibly with explanation', 'code', 'code text'),
    C('doc_prose', 'docs', 'explanatory documentation text', 'prose', 'text'),
    C('callout_note', 'docs', 'note, warning, tip or pitfall box', 'prose', 'kind text'),
    C('install_instructions', 'docs', 'install or setup commands', 'code', 'code text', heading='Install'),
    C('changelog_entry', 'docs', 'release notes for a version', 'bullets', 'version date items'),
    C('compat_table', 'docs', 'browser or version compatibility table', 'table', 'rows', heading='Compatibility'),
    C('readme_badges', 'docs', 'status badges and shields', 'drop'),
    C('repo_header', 'docs', 'code repository name, description, stars, forks', 'header', 'name description stars forks language', 'SoftwareSourceCode'),
    C('file_tree', 'docs', 'list of files and folders in a repository', 'drop'),
    C('cli_reference', 'docs', 'command line usage and flags', 'code', 'code text'),
    # ---- community
    C('thread_header', 'community', 'forum or Q&A question title, author, stats', 'header', 'title author date votes answers views', 'QAPage DiscussionForumPosting'),
    C('post_body', 'community', 'body of a forum post or question', 'prose', 'author date text'),
    C('answer', 'community', 'one answer or reply with author and votes', 'prose', 'author votes date text', 'Answer Comment'),
    C('comment_list', 'community', 'comments under a post', 'prose', 'items', heading='Comments'),
    C('social_post', 'community', 'tweet, post or status with author and counts', 'prose', 'author date text likes reposts replies', 'SocialMediaPosting'),
    C('poll', 'community', 'poll question and options with votes', 'kv', 'question options'),
    C('community_rules', 'community', 'rules or guidelines of a forum or group', 'bullets', 'items', heading='Rules'),
    C('subreddit_header', 'community', 'community or group name, members, description', 'header', 'name members description'),
    # ---- profile
    C('profile_header', 'profile', 'person or account name, handle, bio, follower counts', 'header', 'name handle bio followers following posts', 'Person ProfilePage'),
    C('org_header', 'profile', 'company or organization name, industry, size, HQ', 'header', 'name industry size headquarters founded website', 'Organization Corporation'),
    C('place_header', 'profile', 'business or place name, address, hours, rating', 'header', 'name address phone hours rating', 'LocalBusiness Restaurant Place'),
    C('experience_list', 'profile', 'jobs or roles held with dates', 'bullets', 'items', heading='Experience'),
    C('education_list', 'profile', 'schools and degrees', 'bullets', 'items', heading='Education'),
    C('skills_list', 'profile', 'skills, tags or specialties', 'bullets', 'items', heading='Skills'),
    C('contact_info', 'profile', 'email, phone, address, social links', 'kv', 'email phone address', heading='Contact'),
    C('opening_hours', 'profile', 'opening hours by day', 'kv', 'hours', heading='Hours'),
    C('post_grid', 'profile', "grid of an account's posts or videos", 'cards', 'items', heading='Posts'),
    C('people_list', 'profile', 'list of people, employees, followers or members', 'cards', 'items', heading='People'),
    # ---- media
    C('video_header', 'media', 'video title, channel, views, date, description', 'header', 'title channel views date duration description', 'VideoObject'),
    C('podcast_episode', 'media', 'podcast or episode title, show, date, summary', 'header', 'title show date duration summary', 'PodcastEpisode'),
    C('film_header', 'media', 'film or show title, year, rating, director, cast', 'header', 'title year rating director cast genre', 'Movie TVSeries'),
    C('book_header', 'media', 'book title, author, rating, pages, published', 'header', 'title author rating pages published', 'Book'),
    C('music_header', 'media', 'song or album title, artist, release', 'header', 'title artist release', 'MusicRecording MusicAlbum'),
    C('game_header', 'media', 'game or app name, developer, rating, platforms', 'header', 'name developer rating platforms', 'VideoGame SoftwareApplication MobileApplication'),
    C('cast_list', 'media', 'cast and crew list', 'bullets', 'items', heading='Cast'),
    C('episode_list', 'media', 'list of episodes or tracks', 'cards', 'items', heading='Episodes'),
    C('transcript', 'media', 'transcript or lyrics text', 'prose', 'text', heading='Transcript'),
    C('genre_tags', 'media', 'genres, tags or categories', 'bullets', 'items', heading='Genres'),
    C('media_player', 'media', 'player controls, timestamps, playback UI', 'drop'),
    # ---- events / travel
    C('event_card', 'events_travel', 'event name, date, time, venue, price', 'kv', 'name date venue price', 'Event'),
    C('ticket_options', 'events_travel', 'ticket types and prices', 'table', 'rows', heading='Tickets'),
    C('hotel_header', 'events_travel', 'hotel or rental name, rating, price per night, location', 'header', 'name rating price location', 'Hotel LodgingBusiness VacationRental'),
    C('amenities_list', 'events_travel', 'amenities or facilities', 'bullets', 'items', heading='Amenities'),
    C('flight_option', 'events_travel', 'flight times, airline, stops, price', 'kv', 'airline depart arrive stops price', 'Flight'),
    C('itinerary', 'events_travel', 'day-by-day plan or schedule', 'steps', 'items', heading='Itinerary'),
    C('booking_policy', 'events_travel', 'cancellation, check-in or house rules', 'kv', 'rules', heading='Policies'),
    # ---- food / health
    C('recipe', 'food_health', 'recipe title, time, servings, rating', 'header', 'name time servings rating', 'Recipe'),
    C('ingredients', 'food_health', 'list of recipe ingredients', 'bullets', 'items', heading='Ingredients'),
    C('instructions', 'food_health', 'numbered cooking or how-to steps', 'steps', 'items', 'HowTo', 'Steps'),
    C('nutrition_facts', 'food_health', 'calories and nutrients', 'kv', 'nutrients', 'NutritionInformation', 'Nutrition'),
    C('menu', 'food_health', 'restaurant menu items and prices', 'cards', 'items', 'Menu', 'Menu'),
    C('medical_info', 'food_health', 'symptoms, dosage, treatment or health facts', 'prose', 'text', 'MedicalCondition Drug'),
    # ---- data / finance
    C('data_table', 'data_finance', 'table of data with rows and columns', 'table', 'rows'),
    C('stat_highlight', 'data_finance', 'big number or key statistic with label', 'kv', 'label value'),
    C('stock_quote', 'data_finance', 'ticker, price, change, market data', 'kv', 'symbol price change volume market_cap'),
    C('chart', 'data_finance', 'chart or graph with its labels', 'prose', 'title text'),
    C('pricing_plans', 'business', 'subscription plans with prices and features', 'table', 'rows', heading='Pricing'),
    # ---- business
    C('hero', 'business', 'headline and tagline at the top of a landing page', 'header', 'headline tagline'),
    C('feature_grid', 'business', 'grid of product features with short descriptions', 'kv', 'features', heading='Features'),
    C('testimonial', 'business', 'customer quote or case study snippet', 'prose', 'author text'),
    C('logo_wall', 'business', 'customer or partner logos', 'drop'),
    C('faq', 'business', 'frequently asked questions and answers', 'qa', 'items', 'FAQPage Question', 'FAQ'),
    C('call_to_action', 'business', 'sign up, get started, contact sales buttons', 'drop'),
    C('team_section', 'business', 'team members with roles', 'cards', 'items', heading='Team'),
    C('timeline', 'reference', 'dated events in order', 'bullets', 'items', heading='Timeline'),
    # ---- reference
    C('infobox', 'reference', 'summary box of key facts about a subject', 'kv', 'facts', heading='Facts'),
    C('definition', 'reference', 'term and its definition', 'kv', 'term definition'),
    C('encyclopedia_section', 'reference', 'section of encyclopedia text under a heading', 'prose', 'text'),
    C('see_also', 'reference', 'see also list of related topics', 'links', 'items', heading='See also'),
    C('citations', 'reference', 'references, footnotes, sources', 'drop'),
    C('disambiguation', 'reference', 'list of meanings for an ambiguous term', 'bullets', 'items'),
    # ---- chrome
    C('navigation', 'chrome', 'site menus, tabs, category lists', 'drop'),
    C('breadcrumb', 'chrome', 'category path like Home > Electronics > Headphones', 'kv', 'path', 'BreadcrumbList'),
    C('footer', 'chrome', 'site footer, copyright, legal and policy links', 'drop'),
    C('promo_ad', 'chrome', 'ads, sponsored items, credit card or upsell offers', 'drop'),
    C('cookie_banner', 'chrome', 'cookie or consent notice', 'drop'),
    C('login_prompt', 'chrome', 'sign in, create account or app download prompt', 'drop'),
    C('share_buttons', 'chrome', 'share, save, like buttons', 'drop'),
    C('ui_chrome', 'chrome', 'loading text, image placeholders, empty widgets, error text', 'drop'),
    C('recommendations', 'chrome', 'customers also bought, you may also like, trending', 'links', 'items'),
]

BY_NAME = {c.name: c for c in CATALOG}
BY_CATEGORY = {cat: [c for c in CATALOG if c.category == cat] for cat in CATEGORIES}
BY_LD = {t: c for c in CATALOG for t in c.ld}
assert len(BY_NAME) == len(CATALOG), 'duplicate component name'
assert all(len(v) <= 255 for v in BY_CATEGORY.values())
