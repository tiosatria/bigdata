import os
import re
import json
from urllib.parse import urlparse, urlunparse, quote_plus, parse_qs, unquote, urljoin
from typing import Set, Dict, Any, Iterable
from collections import deque, defaultdict

import scrapy


class WPDiscoverSpider(scrapy.Spider):
    name = 'wp_discover'

    custom_settings = {
        'CONCURRENT_REQUESTS': 1000,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2,
        'DOWNLOAD_DELAY': 1.0,
        'RETRY_TIMES': 3,
        'COMPRESSION_ENABLED': False,
        'HTTP2_ENABLED': False,
        'CLOSESPIDER_TIMEOUT': 0,  # Disable timeout - run indefinitely
        'CLOSESPIDER_ITEMCOUNT': 0,  # Disable item count limit
        'CLOSESPIDER_PAGECOUNT': 0,  # Disable page count limit
    }

    DEFAULT_TOPICS = [
        # Home & Living
        'home cleaning tips stain removal hacks',
        'organization storage solutions decluttering',
        'interior design home decor ideas',
        'furniture restoration DIY projects',
        'gardening plant care landscaping',
        'home maintenance repair tutorials',

        # Cooking & Food
        'cooking recipes meal prep ideas',
        'baking tips dessert recipes',
        'food preservation canning freezing',
        'kitchen hacks cooking techniques',
        'healthy eating nutrition tips',
        'budget meals frugal cooking',
        'international cuisine ethnic recipes',
        'vegan vegetarian plant-based recipes',

        # Health & Wellness
        'natural remedies home treatments',
        'fitness workout routines exercise',
        'mental health self-care wellness',
        'nutrition diet healthy lifestyle',
        'beauty skincare natural products',
        'sleep improvement relaxation techniques',
        'stress management mindfulness meditation',

        # DIY & Crafts
        'handmade crafts DIY tutorials',
        'woodworking projects plans',
        'sewing patterns clothing alterations',
        'upcycling repurposing creative reuse',
        'jewelry making beading crafts',
        'painting drawing art techniques',
        'home improvement renovation DIY',
 
        # Lifestyle & Personal
        'parenting tips child development',
        'pregnancy baby care newborn',
        'pet care training animal health',
        'personal finance budgeting saving',
        'productivity time management hacks',
        'relationship advice communication tips',
        'travel tips destination guides',

        # Technology & Digital
        'tech tips computer troubleshooting',
        'smartphone apps productivity tools',

        # Fashion & Style
        'fashion trends style guides',
        'wardrobe essentials outfit ideas',
        'sustainable fashion ethical clothing',
        'makeup tutorials beauty tips',

        # Education & Learning
        'study tips learning techniques',
        'online courses skill development',
        'language learning resources',
        'book reviews reading recommendations',

        # Entertainment & Hobbies
        'gaming tips strategies guides',
        'collectibles hobby ideas',

        # Business & Career
        'entrepreneurship startup advice',
        'resume writing job search tips',
        'small business marketing ideas',

        # Miscellaneous
        'life hacks productivity tips',
        'seasonal tips holiday ideas',
        'sustainability eco-friendly living',
        'minimalism simple living',
    ]

    def __init__(self,
                 search_words: str = None,
                 engine: str = None,
                 engines: str = 'bing,yahoo',
                 existing_path: str = None,
                 output_path: str = None,
                 continuous: bool = True,
                 max_pages_per_query: int = 20,
                 verify_backlog_threshold: int = 50,
                 verify_backlog_resume: int = None,
                 *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Determine keywords
        if search_words:
            self.keywords = [w.strip() for w in re.split(r'[;,]', search_words) if w.strip()]
        else:
            self.keywords = list(self.DEFAULT_TOPICS)

        # Engine selection
        if engines:
            eng_list = [e.strip().lower() for e in re.split(r'[;,\s]+', engines) if e.strip()]
        else:
            e = (engine or '').strip().lower()
            eng_list = [e] if e else []
        if not eng_list:
            # eng_list = ['duckduckgo', 'bing', 'google', 'yahoo']
            eng_list = ['bing', 'yahoo']

        valid = {'duckduckgo', 'bing', 'google', 'yahoo'}
        self.engines = [e for e in eng_list if e in valid]
        if not self.engines:
            # self.engines = ['duckduckgo', 'bing', 'google', 'yahoo']
            self.engines = ['bing', 'yahoo']

        # Paths
        self.project_root = os.getcwd()
        self.existing_path = existing_path or os.path.join('target', 'existing.txt')
        self.output_path = output_path or os.path.join('target', 'new_target.txt')
        self.continuous = bool(continuous) if isinstance(continuous, bool) else str(continuous).lower() not in {'0',
                                                                                                                'false',
                                                                                                                'no'}
        self.max_pages_per_query = int(max_pages_per_query)

        # State tracking
        self.existing_domains: Set[str] = set()
        self.already_output: Set[str] = set()
        self.discovered: Set[str] = set()

        # Verification backlog control (hysteresis)
        self.verify_backlog_threshold: int = int(verify_backlog_threshold)  # high watermark to start deferring pagination
        if verify_backlog_resume is None:
            self.verify_backlog_resume: int = max(1, self.verify_backlog_threshold // 2)  # low watermark to resume
        else:
            self.verify_backlog_resume: int = int(verify_backlog_resume)
        self.pending_verifications: int = 0
        self.pagination_queues: Dict[str, deque] = defaultdict(deque)

        # Pagination tracking per keyword+engine
        self.page_counts: Dict[str, int] = {}
        self.empty_page_counts: Dict[str, int] = {}

        # Stats for logging
        self.stats = {
            'searches_initiated': 0,
            'pages_crawled': 0,
            'domains_discovered': 0,
            'wp_sites_confirmed': 0,
        }

        # Persistent pagination state
        self.state_dir = os.path.join('crawl_state')
        os.makedirs(self.state_dir, exist_ok=True)
        self.state_path = os.path.join(self.state_dir, 'wp_discover_state.json')
        self.pagination_state: Dict[str, Any] = {}
        self._load_pagination_state()

        # Prepare files/sets
        self._load_existing()
        self._load_output_seen()
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

        self.logger.info(f"[INIT] Loaded {len(self.existing_domains)} existing domains")
        self.logger.info(f"[INIT] Loaded {len(self.already_output)} already output domains")
        self.logger.info(f"[INIT] Keywords: {len(self.keywords)}, Engines: {self.engines}")
        self.logger.info(f"[INIT] Continuous mode: {self.continuous}, Max pages per query: {self.max_pages_per_query}")
        self.logger.info(f"[INIT] Loaded pagination state for {len(self.pagination_state)} keys from {self.state_path}")

    # ------------- Utilities -------------
    def _load_pagination_state(self):
        try:
            if os.path.exists(self.state_path):
                with open(self.state_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        self.pagination_state = data
        except Exception as e:
            self.logger.error(f"[STATE] Failed to load pagination state from {self.state_path}: {e}")

    def _save_pagination_state(self):
        try:
            tmp_path = self.state_path + '.tmp'
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump(self.pagination_state, f, ensure_ascii=False)
            # Atomic replace
            try:
                os.replace(tmp_path, self.state_path)
            except Exception:
                # Fallback on Windows if rename issues
                if os.path.exists(self.state_path):
                    os.remove(self.state_path)
                os.rename(tmp_path, self.state_path)
        except Exception as e:
            self.logger.error(f"[STATE] Failed to save pagination state to {self.state_path}: {e}")

    def _state_key(self, kw: str, engine: str) -> str:
        return f"{engine}:{kw}"

    def _get_resume_value(self, kw: str, engine: str, default_value: int) -> int:
        key = self._state_key(kw, engine)
        try:
            entry = self.pagination_state.get(key)
            if isinstance(entry, dict) and 'next' in entry:
                return int(entry.get('next') or default_value)
        except Exception:
            pass
        return int(default_value)

    def _set_resume_value(self, kw: str, engine: str, next_value: int):
        key = self._state_key(kw, engine)
        try:
            self.pagination_state[key] = {'next': int(next_value)}
            self._save_pagination_state()
        except Exception as e:
            self.logger.error(f"[STATE] Failed to set resume value for {key}: {e}")

    def _normalize_domain(self, url_like: str) -> str:
        """Return a clean domain (netloc) from a URL or text."""
        if not url_like:
            return ''
        u = url_like.strip()
        if not u:
            return ''

        # Extract target from SERP redirects first
        extracted = self._extract_target_from_serp(u)
        if extracted:
            u = extracted

        # Prepend scheme if needed
        if not re.match(r'^https?://', u, flags=re.I):
            u = 'https://' + u

        try:
            p = urlparse(u)
        except Exception:
            return ''

        netloc = (p.netloc or p.path or '').lower()

        # Handle protocol-relative
        if netloc.startswith('//'):
            netloc = netloc[2:]

        # Keep only hostname part before first '/'
        if '/' in netloc:
            netloc = netloc.split('/', 1)[0]

        # Strip www.
        if netloc.startswith('www.'):
            netloc = netloc[4:]

        # Strip port
        if ':' in netloc:
            netloc = netloc.split(':', 1)[0]

        # Basic validation
        if not netloc or '.' not in netloc or ' ' in netloc:
            return ''

        # Ignore search engine hosts
        bad_suffixes = (
            '.duckduckgo.com', '.bing.com', '.google.com', '.yahoo.com',
            'duckduckgo.com', 'bing.com', 'google.com', 'yahoo.com'
        )
        if any(netloc == sfx or netloc.endswith(sfx) for sfx in bad_suffixes):
            return ''

        return netloc

    def _load_existing(self):
        try:
            with open(self.existing_path, 'r', encoding='utf-8') as f:
                for line in f:
                    dom = self._normalize_domain(line.strip())
                    if dom:
                        self.existing_domains.add(dom)
        except FileNotFoundError:
            self.logger.warning(f"[LOAD] Existing list not found: {self.existing_path}")
        except Exception as e:
            self.logger.error(f"[LOAD] Error reading existing_path {self.existing_path}: {e}")

    def _load_output_seen(self):
        try:
            with open(self.output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    dom = self._normalize_domain(line.strip())
                    if dom:
                        self.already_output.add(dom)
        except FileNotFoundError:
            pass
        except Exception as e:
            self.logger.error(f"[LOAD] Error reading output_path {self.output_path}: {e}")

    def _append_new_target(self, domain: str):
        if not domain:
            return
        if domain in self.already_output:
            return
        try:
            with open(self.output_path, 'a', encoding='utf-8') as f:
                f.write(domain + "\n")
            self.already_output.add(domain)
            self.stats['wp_sites_confirmed'] += 1
            self.logger.info(f"[NEW TARGET #{self.stats['wp_sites_confirmed']}] {domain}")
        except Exception as e:
            self.logger.error(f"[ERROR] Failed to append target {domain}: {e}")

    def _build_wp_posts_url(self, base_url: str) -> str:
        p = urlparse('https://' + base_url if not re.match(r'^https?://', base_url) else base_url)
        scheme = p.scheme or 'https'
        netloc = p.netloc or p.path
        base = urlunparse((scheme, netloc, '', '', '', ''))
        return f"{base}/wp-json/wp/v2/posts?per_page=1&page=1"

    def _default_headers(self) -> Dict[str, str]:
        return {
            'Accept': 'application/json, text/javascript, */*; q=0.1',
            'Accept-Language': 'en-US,en;q=0.8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
            'Cache-Control': 'no-cache',
        }

    def _validate_wp_headers(self, response: scrapy.http.Response) -> bool:
        total_pages_hdr = response.headers.get(b'X-WP-TotalPages') or response.headers.get(b'x-wp-totalpages')
        total_hdr = response.headers.get(b'X-WP-Total') or response.headers.get(b'x-wp-total')
        if not total_pages_hdr or not total_hdr:
            return False
        try:
            int(total_pages_hdr.decode() if isinstance(total_pages_hdr, (bytes, bytearray)) else total_pages_hdr)
            int(total_hdr.decode() if isinstance(total_hdr, (bytes, bytearray)) else total_hdr)
            return True
        except Exception:
            return False

    def _get_page_key(self, kw: str, engine: str) -> str:
        """Generate unique key for tracking pagination per keyword+engine."""
        return f"{engine}:{kw}"

    def _should_continue_pagination(self, kw: str, engine: str, found_results: bool) -> bool:
        """Determine if we should continue paginating for this keyword+engine."""
        if not self.continuous:
            return False

        key = self._get_page_key(kw, engine)
        current_page = self.page_counts.get(key, 0)

        # Stop if we've hit max pages
        if current_page >= self.max_pages_per_query:
            self.logger.info(
                f"[PAGINATION STOP] {engine.upper()} '{kw}' - reached max pages ({self.max_pages_per_query})")
            return False

        # Track empty pages
        if not found_results:
            self.empty_page_counts[key] = self.empty_page_counts.get(key, 0) + 1
            # Stop after 2 consecutive empty pages
            if self.empty_page_counts[key] >= 2:
                self.logger.info(
                    f"[PAGINATION STOP] {engine.upper()} '{kw}' - 2 consecutive empty pages at page {current_page}")
                return False
        else:
            # Reset empty counter if we found results
            self.empty_page_counts[key] = 0

        return True

    def _increment_page(self, kw: str, engine: str):
        """Increment page counter for keyword+engine."""
        key = self._get_page_key(kw, engine)
        self.page_counts[key] = self.page_counts.get(key, 0) + 1

    # ------------- Backlog-aware pagination helpers -------------
    def _queue_key(self, kw: str, engine: str) -> str:
        return f"{engine}:{kw}"

    def _defer_or_emit_pagination(self, kw: str, engine: str, request: scrapy.Request):
        """Either return pagination request now or defer it based on verification backlog with hysteresis."""
        key = self._queue_key(kw, engine)
        # If backlog is above or equal to high watermark, defer pagination
        if self.pending_verifications >= self.verify_backlog_threshold:
            self.pagination_queues[key].append(request)
            self.logger.info(
                f"[PAGINATION DEFERRED] {engine.upper()} '{kw}' - backlog={self.pending_verifications} "+
                f">= threshold={self.verify_backlog_threshold}, queued={len(self.pagination_queues[key])}"
            )
            return None
        # else allow emit now
        return request

    def _drain_pagination_if_possible(self, kw: str, engine: str):
        """Pop and return one deferred pagination request if backlog allows using hysteresis low watermark."""
        # Only resume if backlog has dropped to or below resume watermark
        if self.pending_verifications > self.verify_backlog_resume:
            return None
        key = self._queue_key(kw, engine)
        if self.pagination_queues[key]:
            req = self.pagination_queues[key].popleft()
            self.logger.info(
                f"[PAGINATION RESUMED] {engine.upper()} '{kw}' - backlog={self.pending_verifications} <= resume={self.verify_backlog_resume}, "
                f"remaining_queue={len(self.pagination_queues[key])}"
            )
            return req
        return None

    # ------------- Start -------------
    def start_requests(self):
        """Generate initial search requests for all keywords and engines."""
        for kw in self.keywords:
            for eng in self.engines:
                self.stats['searches_initiated'] += 1

                # if eng == 'duckduckgo':
                #     url = f"https://html.duckduckgo.com/html/?q={quote_plus(kw)}&s=0"
                #     meta = {
                #         'kw': kw, 's': 0, 'engine': 'duckduckgo',
                #         'bypass_cf': True, 'use_proxy': False
                #     }
                #     self.logger.info(f"[SEARCH START] DDG '{kw}' - page 1")
                #     yield scrapy.Request(url, meta=meta, callback=self.parse_search_ddg,
                #                          dont_filter=True, errback=self.errback_search)

                if eng == 'bing':
                    start_offset = self._get_resume_value(kw, 'bing', 1)
                    url = f"https://www.bing.com/search?q={quote_plus(kw)}&count=50&first={start_offset}"
                    meta = {
                        'kw': kw, 'offset': start_offset, 'engine': 'bing',
                        'use_proxy': False, 'bypass_cf': True
                    }
                    page_num = ((start_offset - 1) // 50) + 1
                    if start_offset > 1:
                        self.logger.info(f"[SEARCH RESUME] BING '{kw}' - resuming at page {page_num} (first={start_offset})")
                    else:
                        self.logger.info(f"[SEARCH START] BING '{kw}' - page 1")
                    yield scrapy.Request(url, meta=meta, callback=self.parse_search_bing,
                                         dont_filter=True, errback=self.errback_search)

                # elif eng == 'google':
                #     url = f"https://www.google.com/search?q={quote_plus(kw)}&num=50&start=0"
                #     meta = {
                #         'kw': kw, 'start': 0, 'engine': 'google',
                #         'use_proxy': False, 'bypass_cf': True
                #     }
                #     self.logger.info(f"[SEARCH START] GOOGLE '{kw}' - page 1")
                #     yield scrapy.Request(url, meta=meta, callback=self.parse_search_google,
                #                          dont_filter=True, errback=self.errback_search)

                elif eng == 'yahoo':
                    url = f"https://search.yahoo.com/search?p={quote_plus(kw)}&b=1"
                    meta = {
                        'kw': kw, 'b': 1, 'engine': 'yahoo',
                        'use_proxy': False, 'bypass_cf': True
                    }
                    self.logger.info(f"[SEARCH START] YAHOO '{kw}' - page 1")
                    yield scrapy.Request(url, meta=meta, callback=self.parse_search_yahoo,
                                         dont_filter=True, errback=self.errback_search)

    def errback_search(self, failure):
        """Handle search request failures."""
        request = failure.request
        kw = request.meta.get('kw', 'unknown')
        engine = request.meta.get('engine', 'unknown')
        self.logger.error(f"[SEARCH ERROR] {engine.upper()} '{kw}' - {failure.value}")

    # ------------- Search Parsers -------------
    def parse_search_bing(self, response: scrapy.http.Response):
        kw = response.meta.get('kw')
        offset = int(response.meta.get('offset') or 1)
        engine = 'bing'

        self._increment_page(kw, engine)
        self.stats['pages_crawled'] += 1
        page_num = self.page_counts[self._get_page_key(kw, engine)]
        self.logger.info(f"[SEARCH PAGE] BING '{kw}' page {page_num} | backlog={self.pending_verifications}")

        # Extract result links
        links = response.css('li.b_algo h2 a::attr(href)').getall()
        self.logger.info(f"[SEARCH RESULT] BING '{kw}' page {page_num} - found {len(links)} links")

        yield from self._handle_search_links(links, kw, engine)

        # Pagination
        if self._should_continue_pagination(kw, engine, bool(links)):
            next_offset = offset + 50
            next_url = f"https://www.bing.com/search?q={quote_plus(kw)}&count=50&first={next_offset}"
            meta = {
                'kw': kw, 'offset': next_offset, 'engine': engine,
                'use_proxy': False, 'bypass_cf': True
            }
            next_req = scrapy.Request(next_url, meta=meta, callback=self.parse_search_bing,
                                 dont_filter=True, errback=self.errback_search, priority=-100)
            maybe = self._defer_or_emit_pagination(kw, engine, next_req)
            if maybe is not None:
                self.logger.info(f"[PAGINATION] BING '{kw}' -> page {page_num + 1}")
                yield maybe

    # disabled for now
    def parse_search_ddg(self, response: scrapy.http.Response):
        kw = response.meta.get('kw')
        s = int(response.meta.get('s') or 0)
        engine = 'duckduckgo'

        self._increment_page(kw, engine)
        self.stats['pages_crawled'] += 1
        page_num = self.page_counts[self._get_page_key(kw, engine)]

        # Extract links
        links = response.css('a.result__a::attr(href)').getall()
        self.logger.info(f"[SEARCH RESULT] DDG '{kw}' page {page_num} - found {len(links)} links")

        yield from self._handle_search_links(links, kw, engine)

        # Pagination
        if self._should_continue_pagination(kw, engine, bool(links)):
            next_s = s + 50
            next_url = f"https://html.duckduckgo.com/html/?q={quote_plus(kw)}&s={next_s}"
            meta = {
                'kw': kw, 's': next_s, 'engine': engine,
                'bypass_cf': True, 'use_proxy': False
            }
            self.logger.info(f"[PAGINATION] DDG '{kw}' -> page {page_num + 1}")
            yield scrapy.Request(next_url, meta=meta, callback=self.parse_search_ddg,
                                 dont_filter=True, errback=self.errback_search)
    # disabled for now
    def parse_search_google(self, response: scrapy.http.Response):
        kw = response.meta.get('kw')
        start = int(response.meta.get('start') or 0)
        engine = 'google'

        self._increment_page(kw, engine)
        self.stats['pages_crawled'] += 1
        page_num = self.page_counts[self._get_page_key(kw, engine)]

        # Extract links
        raw_links = response.css('a[href^="/url?"]::attr(href), div.yuRUbf > a::attr(href)').getall()
        self.logger.info(f"[SEARCH RESULT] GOOGLE '{kw}' page {page_num} - found {len(raw_links)} links")

        yield from self._handle_search_links(raw_links, kw, engine)

        # Pagination
        if self._should_continue_pagination(kw, engine, bool(raw_links)):
            next_start = start + 50
            next_url = f"https://www.google.com/search?q={quote_plus(kw)}&num=50&start={next_start}"
            meta = {
                'kw': kw, 'start': next_start, 'engine': engine,
                'use_proxy': False, 'bypass_cf': True
            }
            self.logger.info(f"[PAGINATION] GOOGLE '{kw}' -> page {page_num + 1}")
            yield scrapy.Request(next_url, meta=meta, callback=self.parse_search_google,
                                 dont_filter=True, errback=self.errback_search)

    def parse_search_yahoo(self, response: scrapy.http.Response):
        kw = response.meta.get('kw')
        b = int(response.meta.get('b') or 1)
        engine = 'yahoo'

        self._increment_page(kw, engine)
        self.stats['pages_crawled'] += 1
        page_num = self.page_counts[self._get_page_key(kw, engine)]

        self.logger.info(f"[SEARCH PAGE] YAHOO '{kw}' page {page_num} | backlog={self.pending_verifications}")
        # Extract links
        links = response.css('div#web li div.compTitle a::attr(href), div.algo h3.title a::attr(href)').getall()
        self.logger.info(f"[SEARCH RESULT] YAHOO '{kw}' page {page_num} - found {len(links)} links")

        yield from self._handle_search_links(links, kw, engine)

        # Pagination
        if self._should_continue_pagination(kw, engine, bool(links)):
            next_b = b + 10
            next_url = f"https://search.yahoo.com/search?p={quote_plus(kw)}&b={next_b}"
            meta = {
                'kw': kw, 'b': next_b, 'engine': engine,
                'use_proxy': False, 'bypass_cf': True
            }
            next_req = scrapy.Request(next_url, meta=meta, callback=self.parse_search_yahoo,
                                 dont_filter=True, errback=self.errback_search, priority=-100)
            maybe = self._defer_or_emit_pagination(kw, engine, next_req)
            if maybe is not None:
                self.logger.info(f"[PAGINATION] YAHOO '{kw}' -> page {page_num + 1}")
                yield maybe

    def _extract_target_from_serp(self, href: str) -> str:
        """Extract real target URL from search engine redirects.
        Extremely defensive: handle percent-encoded, double-encoded, and base64-wrapped targets.
        """
        if not href:
            return ''
        h = href.strip()

        # Normalize protocol-relative
        if h.startswith('//'):
            h = 'https:' + h

        try:
            pu = urlparse(h)
        except Exception:
            return ''

        host = (pu.netloc or '').lower()
        path = (pu.path or '').strip('/')

        # Helpers
        def _unquote_multi(s: str, times: int = 2) -> str:
            try:
                out = s
                for _ in range(times):
                    out = unquote(out)
                return out
            except Exception:
                return s

        def _maybe_b64_decode(s: str) -> str:
            """Try urlsafe and standard base64 decoding if not already http."""
            try:
                import base64
                ss = s.strip()
                if not ss or ss.lower().startswith('http'):
                    return ss
                # urlsafe first
                pad = (-len(ss)) % 4
                if pad:
                    ss_padded = ss + ('=' * pad)
                else:
                    ss_padded = ss
                for decoder in (base64.urlsafe_b64decode, base64.b64decode):
                    try:
                        decoded = decoder(ss_padded.encode('ascii', errors='ignore')).decode('utf-8', errors='ignore')
                        if decoded:
                            return decoded
                    except Exception:
                        pass
                return s
            except Exception:
                return s

        def _find_http_in_text(text: str) -> str:
            """Find first http(s):// URL in text, including percent-encoded forms."""
            if not text:
                return ''
            t = _unquote_multi(text, 2)
            # Direct http
            m = re.search(r'https?://[^\s"\'\)]+', t)
            if m:
                return m.group(0)
            # Percent-encoded http(s)
            m = re.search(r'https?%3A%2F%2F[^\s&]+', text, flags=re.I)
            if m:
                return _unquote_multi(m.group(0), 2)
            return ''

        # If already a normal external URL (not a search host), return as-is
        if host and not any(host.endswith(sfx) or host == sfx for sfx in (
            'duckduckgo.com','bing.com','google.com','yahoo.com','r.msn.com','msn.com','search.yahoo.com','r.search.yahoo.com'
        )):
            return h

        # DuckDuckGo /l redirect
        if host.endswith('duckduckgo.com') and path.lower() == 'l':
            qs = parse_qs(pu.query or '')
            uddg = qs.get('uddg', [''])[0]
            if uddg:
                url = _unquote_multi(uddg, 2)
                if not url.lower().startswith('http'):
                    url = _maybe_b64_decode(url)
                return url if url.lower().startswith('http') else ''

        # Google /url redirect
        if host.endswith('google.com') and path.lower() == 'url':
            qs = parse_qs(pu.query or '')
            q = qs.get('q', [''])[0]
            if q:
                url = _unquote_multi(q, 2)
                return url if url.lower().startswith('http') else ''

        # Yahoo redirects (query params and path-embedded RU=)
        if host.endswith('yahoo.com') or host.endswith('search.yahoo.com') or host.endswith('r.search.yahoo.com'):
            qs = parse_qs(pu.query or '')
            ru = qs.get('RU', [''])[0] or qs.get('ru', [''])[0] or qs.get('u', [''])[0]
            if ru:
                url = _unquote_multi(ru, 2)
                if not url.lower().startswith('http'):
                    url = _maybe_b64_decode(url)
                if not url.lower().startswith('http'):
                    url = _find_http_in_text(url)
                return url if url.lower().startswith('http') else ''
            # Path-embedded RU=
            try:
                m = re.search(r'/RU=([^/]+)', pu.path)
                if m:
                    enc = m.group(1)
                    url = _unquote_multi(enc, 2)
                    if not url.lower().startswith('http'):
                        url = _find_http_in_text(url)
                    return url if url.lower().startswith('http') else ''
            except Exception:
                pass

        # Bing redirects (e.g., /ck/a, /aclick, /l) and MSN wrappers
        if host.endswith('bing.com'):
            qs = parse_qs(pu.query or '')
            # Common params carrying target URL in Bing
            for key in ('q', 'u', 'url', 'r', 'to', 'target', 'dest'):
                val = qs.get(key, [''])[0]
                if val:
                    url = _unquote_multi(val, 2)
                    if not url.lower().startswith('http'):
                        url = _maybe_b64_decode(url)
                    if not url.lower().startswith('http'):
                        url = _find_http_in_text(url)
                    if url.lower().startswith('http'):
                        return url
            # Some Bing links embed the URL in the path after /l/ or /ck/a/.../url=<enc>
            if path.lower().startswith('l/'):
                tail = h.split('l/', 1)[-1]
                url = _unquote_multi(tail, 2)
                if not url.lower().startswith('http'):
                    url = _maybe_b64_decode(url)
                if not url.lower().startswith('http'):
                    url = _find_http_in_text(url)
                return url if url.lower().startswith('http') else ''
            # Generic: search any http in full href
            any_url = _find_http_in_text(h)
            if any_url:
                return any_url

        if host.endswith('msn.com') or host.endswith('r.msn.com'):
            qs = parse_qs(pu.query or '')
            for key in ('ru', 'r', 'u', 'url', 'to', 'dest'):
                val = qs.get(key, [''])[0]
                if val:
                    url = _unquote_multi(val, 2)
                    if not url.lower().startswith('http'):
                        url = _maybe_b64_decode(url)
                    if not url.lower().startswith('http'):
                        url = _find_http_in_text(url)
                    if url.lower().startswith('http'):
                        return url
            any_url = _find_http_in_text(h)
            if any_url:
                return any_url

        # Last resort: find an http(s) URL anywhere in the string
        fallback = _find_http_in_text(h)
        return fallback if fallback.lower().startswith('http') else ''

    def _handle_search_links(self, links: Iterable[str], kw: str, engine: str):
        """Process search result links and verify WordPress sites."""
        seen: Set[str] = set()
        new_discoveries = 0
        filtered_non_http = 0
        filtered_search_hosts = 0
        filtered_known = 0
        filtered_duplicate = 0
        sample_search_host_href = None
        sample_invalid_href = None

        for href in links:
            # Extract real target
            real_href = self._extract_target_from_serp(href) or href
            dom = self._normalize_domain(real_href)

            if not dom:
                # differentiate between non-http/invalid and search-host filtered by checking original
                try:
                    pu = urlparse(real_href if re.match(r'^https?://', real_href, flags=re.I) else 'http://' + real_href)
                    host = (pu.netloc or pu.path or '').lower()
                except Exception:
                    host = ''
                if host.endswith(('duckduckgo.com','bing.com','google.com','yahoo.com','msn.com','r.msn.com','search.yahoo.com','r.search.yahoo.com')):
                    filtered_search_hosts += 1
                    if sample_search_host_href is None:
                        sample_search_host_href = href
                else:
                    filtered_non_http += 1
                    if sample_invalid_href is None:
                        sample_invalid_href = href
                continue
            if dom in seen:
                filtered_duplicate += 1
                continue
            seen.add(dom)

            # Skip if already known
            if dom in self.existing_domains or dom in self.already_output or dom in self.discovered:
                filtered_known += 1
                continue

            self.discovered.add(dom)
            new_discoveries += 1
            self.stats['domains_discovered'] += 1

            # Verify WordPress via REST API
            api_url = self._build_wp_posts_url(dom)
            meta = {
                'candidate_domain': dom,
                'use_proxy': True,  # Use proxy for WP verification, not CF bypass
                'bypass_cf': False,
                'body_type': 'json/wordpress/probe',
                'kw': kw,
                'engine': engine,
            }
            # increment backlog and log
            self.pending_verifications += 1
            self.logger.info(f"[VERIFY SCHEDULED] {engine.upper()} '{kw}' -> {dom} | backlog={self.pending_verifications}")
            yield scrapy.Request(
                api_url,
                headers=self._default_headers(),
                meta=meta,
                callback=self.parse_verify_wp,
                errback=self.errback_verify_wp,
                dont_filter=True,
                priority=100
            )

        if new_discoveries > 0:
            self.logger.info(
                f"[DISCOVERY] {engine.upper()} '{kw}' - {new_discoveries} new domains queued for verification")
        elif links:
            # All links filtered; help diagnose with counters and a sample href
            extra = ''
            if filtered_search_hosts and sample_search_host_href:
                extra += f" | sample_search_host_href={sample_search_host_href}"
            if filtered_non_http and sample_invalid_href:
                extra += f" | sample_invalid_href={sample_invalid_href}"
            self.logger.info(
                f"[DISCOVERY] {engine.upper()} '{kw}' - 0 queued | filtered: non_http/invalid={filtered_non_http}, search_hosts={filtered_search_hosts}, duplicates={filtered_duplicate}, known={filtered_known}{extra}")

    # ------------- Verification -------------
    def parse_verify_wp(self, response: scrapy.http.Response):
        dom = response.meta.get('candidate_domain')
        kw = response.meta.get('kw')
        engine = response.meta.get('engine')

        # decrement backlog first
        if self.pending_verifications > 0:
            self.pending_verifications -= 1
        self.logger.info(f"[VERIFY RESULT] {engine.upper()} '{kw}' -> {dom} | status={response.status} | backlog={self.pending_verifications}")

        if response.status == 200 and self._validate_wp_headers(response):
            self._append_new_target(dom)
            # try to drain one pagination if backlog allows
            req = self._drain_pagination_if_possible(kw, engine)
            if req is not None:
                yield req
            return

        # Soft check: valid JSON list response
        if response.status == 200:
            try:
                data = json.loads((response.text or '').strip() or '{}')
                if isinstance(data, list) and len(data) > 0:
                    self._append_new_target(dom)
                    req = self._drain_pagination_if_possible(kw, engine)
                    if req is not None:
                        yield req
                    return
            except Exception:
                pass

        self.logger.info(f"[VERIFY FAIL] {dom} - status {response.status} | backlog={self.pending_verifications}")
        req = self._drain_pagination_if_possible(kw, engine)
        if req is not None:
            yield req

    def errback_verify_wp(self, failure):
        """Handle WP verification failures."""
        request = failure.request
        dom = request.meta.get('candidate_domain', 'unknown')
        kw = request.meta.get('kw')
        engine = request.meta.get('engine')
        if self.pending_verifications > 0:
            self.pending_verifications -= 1
        self.logger.error(f"[VERIFY ERROR] {engine.upper() if engine else engine} '{kw}' -> {dom} | {failure.value} | backlog={self.pending_verifications}")
        req = self._drain_pagination_if_possible(kw, engine)
        if req is not None:
            yield req

    def closed(self, reason):
        """Log stats when spider closes."""
        self.logger.info(f"[SPIDER CLOSED] Reason: {reason}")
        self.logger.info(f"[STATS] Searches initiated: {self.stats['searches_initiated']}")
        self.logger.info(f"[STATS] Search pages crawled: {self.stats['pages_crawled']}")
        self.logger.info(f"[STATS] Unique domains discovered: {self.stats['domains_discovered']}")
        self.logger.info(f"[STATS] WordPress sites confirmed: {self.stats['wp_sites_confirmed']}")