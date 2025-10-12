from datetime import datetime
from urllib.parse import urlparse
import random
import logging

from scrapy.spiders import CrawlSpider, Rule
from scrapy_redis.spiders import RedisCrawlSpider
from scrapy.linkextractors import LinkExtractor
from scrapy.http import Request
from scrapy.exceptions import IgnoreRequest
from twisted.internet.error import TimeoutError, TCPTimedOutError

from bigdata.domain_configs import DomainConfigRegistry
from bigdata.domain_configs.domain_config import RenderEngine
from bigdata.items import ArticleItem
from lxml import etree, html


class ArticleSpider(RedisCrawlSpider):
    """
    Production-grade article spider with comprehensive error handling
    """

    name = 'article'
    redis_key = 'article:start_urls'

    redis_batch_size = 50

    # Track pagination depth per domain
    pagination_depth = {}

    # Proxy rotation state
    proxy_index = {}

    custom_settings = {
        'RETRY_ENABLED': True,
        'RETRY_TIMES': 5,
        'RETRY_HTTP_CODES': [403, 429, 500, 502, 503, 504, 520, 524],
        'RETRY_PRIORITY_ADJUST': 10,
    }

    # Rules will be generated dynamically
    rules = ()

    def __init__(self, *args, **kwargs):
        # Load domain configurations BEFORE calling super().__init__
        DomainConfigRegistry.load_all_configs()

        # Generate rules before spider initialization
        self._generate_rules()

        # Now initialize parent
        super().__init__(*args, **kwargs)

        # Now self.logger is available
        self.logger.info(f"Spider initialized with {len(self.rules)} rules")


    def _generate_rules(self):
        """Generate crawling rules from all registered domain configs"""
        rules = []
        all_domains = DomainConfigRegistry.get_all_domains()

        # Use a temporary logger since self.logger isn't available yet
        temp_logger = logging.getLogger('article_spider')
        temp_logger.info(f"Generating rules for {len(all_domains)} domains")

        # Create pagination rules for all domains
        for domain in all_domains:
            config = DomainConfigRegistry.get(domain)

            if not config.active:
                temp_logger.info(f"Skipping inactive domain: {domain}")
                continue

            if config.pagination_xpath:
                rules.append(
                    Rule(
                        LinkExtractor(
                            allow_domains=[domain],
                            restrict_xpaths=config.pagination_xpath
                        ),
                        follow=True,
                        process_request='process_pagination_request',
                        errback='errback_httpbin'
                    )
                )
                temp_logger.debug(f"Added pagination rule for {domain}")

        # Create article extraction rules for all domains
        for domain in all_domains:
            config = DomainConfigRegistry.get(domain)

            if not config.active:
                continue

            if config.article_links_xpath:
                rules.append(
                    Rule(
                        LinkExtractor(
                            allow_domains=[domain],
                            restrict_xpaths=config.article_links_xpath
                        ),
                        callback='parse_item',
                        process_request='process_article_request',
                        errback='errback_httpbin'
                    )
                )
                temp_logger.debug(f"Added article rule for {domain}")

        self.rules = tuple(rules)
        temp_logger.info(f"Generated {len(self.rules)} rules total")

    def process_pagination_request(self, request, response):
        """Process pagination requests with depth tracking"""
        domain = urlparse(request.url).netloc.replace('www.', '')
        config = DomainConfigRegistry.get(domain)

        if not config:
            self.logger.warning(f"No config for {domain}, using defaults")
            return request

        # Track pagination depth
        depth_key = f"{domain}:{request.url}"
        current_depth = self.pagination_depth.get(depth_key, 0)

        # Check max pages limit
        if config.max_pages and current_depth >= config.max_pages:
            self.logger.info(f"Max pagination depth reached for {domain}: {current_depth}")
            raise IgnoreRequest(f"Max pagination depth {config.max_pages} reached")

        self.pagination_depth[depth_key] = current_depth + 1

        # Apply configuration
        request = self._apply_domain_config(request, config)
        request.meta['pagination_depth'] = current_depth + 1
        request.meta['is_pagination'] = True
        request.meta['domain'] = domain
        request.errback = self.errback_httpbin

        self.logger.debug(f"Processing pagination: {request.url} (depth: {current_depth + 1})")

        return request

    def process_article_request(self, request, response):
        """Process article requests"""
        domain = urlparse(request.url).netloc.replace('www.', '')
        config = DomainConfigRegistry.get(domain)

        if not config:
            self.logger.warning(f"No config for {domain}, using defaults")
            return request

        request = self._apply_domain_config(request, config)
        request.meta['is_article'] = True
        request.meta['domain'] = domain
        request.errback = self.errback_httpbin

        return request

    def _apply_domain_config(self, request, config):
        """Apply domain-specific configuration to request"""

        # Set download delay
        request.meta['download_delay'] = config.download_delay

        # Apply proxy if configured
        if config.proxy_config.enabled:
            proxy = self._get_proxy(config)
            if proxy:
                request.meta['proxy'] = proxy
                self.logger.debug(f"Using proxy {proxy} for {request.url}")

        # Use Playwright if configured
        if config.render_engine == RenderEngine.PLAYWRIGHT:
            request.meta['playwright'] = True
            request.meta['playwright_include_page'] = False

            # Wait for specific selectors if configured
            if config.bot_protection.wait_for_selectors:
                request.meta['playwright_page_methods'] = []
                for selector in config.bot_protection.wait_for_selectors:
                    request.meta['playwright_page_methods'].append({
                        'method': 'wait_for_selector',
                        'selector': selector,
                        'timeout': config.playwright_timeout
                    })

            request.meta['playwright_page_goto_kwargs'] = {
                'wait_until': config.playwright_wait_until,
                'timeout': config.playwright_timeout
            }

            request.meta['playwright_context_kwargs'] = {
                'ignore_https_errors': True,
            }

            # Stealth mode
            if config.bot_protection.use_stealth_mode:
                request.meta['playwright_context_kwargs']['user_agent'] = (
                    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                    'AppleWebKit/537.36 (KHTML, like Gecko) '
                    'Chrome/120.0.0.0 Safari/537.36'
                )

        # Set retry configuration
        request.meta['max_retry_times'] = config.retry_config.max_retries
        request.meta['retry_http_codes'] = config.retry_config.retry_http_codes
        request.meta['backoff_factor'] = config.retry_config.backoff_factor

        return request

    def _get_proxy(self, config):
        """Get proxy based on rotation strategy"""
        if not config.proxy_config.proxy_list:
            return None

        strategy = config.proxy_config.rotation_strategy
        domain_key = config.domain

        if strategy == "random":
            return random.choice(config.proxy_config.proxy_list)

        elif strategy == "round_robin":
            if domain_key not in self.proxy_index:
                self.proxy_index[domain_key] = 0

            proxy = config.proxy_config.proxy_list[self.proxy_index[domain_key]]
            self.proxy_index[domain_key] = (
                    (self.proxy_index[domain_key] + 1) % len(config.proxy_config.proxy_list)
            )
            return proxy

        elif strategy == "sticky":
            if domain_key not in self.proxy_index:
                self.proxy_index[domain_key] = 0
            return config.proxy_config.proxy_list[self.proxy_index[domain_key]]

        return None

    def errback_httpbin(self, failure):
        """Handle request failures"""
        request = failure.request
        domain = request.meta.get('domain') or urlparse(request.url).netloc.replace('www.', '')

        self.logger.error(f"Request failed for {request.url}: {failure.value}")

        # Check if it's a critical error (403, bot detection, etc.)
        if hasattr(failure.value, 'response'):
            response = failure.value.response

            if response.status == 403:
                self.logger.critical(
                    f"\n{'=' * 60}\n"
                    f"🚨 IMMEDIATE ATTENTION REQUIRED 🚨\n"
                    f"{'=' * 60}\n"
                    f"Domain: {domain}\n"
                    f"URL: {request.url}\n"
                    f"Status: 403 Forbidden\n"
                    f"Possible bot detection or IP ban\n"
                    f"Request has been re-queued for retry\n"
                    f"{'=' * 60}"
                )

                # Re-queue the request to Redis with higher priority
                self._requeue_request(request, priority=100)

            elif response.status == 429:
                retry_after = response.headers.get(b'Retry-After', b'60').decode('utf-8')
                self.logger.warning(
                    f"\n{'=' * 60}\n"
                    f"⚠️  Rate limit hit for {domain}\n"
                    f"URL: {request.url}\n"
                    f"Retry-After: {retry_after}s\n"
                    f"Backing off and re-queuing\n"
                    f"{'=' * 60}"
                )
                self._requeue_request(request, priority=50)

            elif response.status >= 500:
                self.logger.warning(
                    f"Server error ({response.status}) for {request.url}, re-queuing"
                )
                self._requeue_request(request, priority=25)

        # Handle timeout errors
        elif isinstance(failure.value, (TimeoutError, TCPTimedOutError)):
            self.logger.warning(f"Timeout for {request.url}, re-queuing")
            self._requeue_request(request, priority=10)

        # Handle other exceptions
        else:
            self.logger.error(
                f"Unknown error for {request.url}: {failure.value}",
                exc_info=failure.value
            )
            # Still try to re-queue
            self._requeue_request(request, priority=5)

    def _requeue_request(self, request, priority=0):
        """Re-queue failed request to Redis"""
        url = request.url

        try:
            # Push back to Redis queue
            # Using rpush to add to end of queue (lower priority)
            # For high priority, we could use lpush
            if priority >= 50:
                # High priority - add to front
                self.server.lpush(self.redis_key, url)
            else:
                # Normal priority - add to back
                self.server.rpush(self.redis_key, url)

            self.logger.info(f"Re-queued {url} with priority {priority}")

        except Exception as e:
            self.logger.error(f"Failed to re-queue {url}: {e}")

    @staticmethod
    def clean_html_fragment(fragment: str, exclude_xpaths: list) -> str:
        """Clean HTML fragment by removing unwanted elements"""
        if not fragment:
            return ""

        try:
            # Parse HTML fragment safely
            doc = html.fromstring(fragment)

            # Remove unwanted nodes
            for xp in exclude_xpaths:
                try:
                    for node in doc.xpath(xp):
                        parent = node.getparent()
                        if parent is not None:
                            parent.remove(node)
                except Exception as e:
                    logging.warning(f"Failed to apply exclude xpath {xp}: {e}")

            # Return serialized, well-formed HTML
            return etree.tostring(doc, encoding="unicode", method="html")

        except Exception as e:
            logging.error(f"Failed to clean HTML fragment: {e}")
            return fragment

    def _detect_bot_protection(self, response, config):
        """Detect if bot protection is active"""
        if not config.bot_protection.enabled:
            return False

        body_text = response.text.lower() if hasattr(response, 'text') else ''

        for selector in config.bot_protection.captcha_detection_selectors:
            try:
                if response.xpath(selector):
                    self.logger.critical(
                        f"\n{'=' * 60}\n"
                        f"🤖 CAPTCHA/Bot Protection Detected 🤖\n"
                        f"{'=' * 60}\n"
                        f"Domain: {config.domain}\n"
                        f"URL: {response.url}\n"
                        f"Selector: {selector}\n"
                        f"Manual intervention may be required\n"
                        f"Consider:\n"
                        f"  - Enabling Playwright with stealth mode\n"
                        f"  - Adding proxy rotation\n"
                        f"  - Increasing download delays\n"
                        f"{'=' * 60}"
                    )
                    return True
            except Exception:
                pass

        # Check for common protection keywords
        protection_keywords = ['captcha', 'cloudflare', 'access denied', 'blocked']
        for keyword in protection_keywords:
            if keyword in body_text:
                self.logger.warning(
                    f"⚠️  Possible bot protection (keyword: '{keyword}') on {response.url}"
                )
                return True

        return False

    def parse_item(self, response):
        """Parse article using domain-specific configuration"""

        # Identify domain from URL
        domain = urlparse(response.url).netloc.replace('www.', '')
        config = DomainConfigRegistry.get(domain)

        if not config:
            self.logger.warning(f"No config found for domain: {domain}")
            return

        # Check for bot protection
        # if self._detect_bot_protection(response, config):
        #     # Re-queue with delay
        #     self._requeue_request(response.request, priority=75)
        #     return

        # Use custom parser if specified
        if config.custom_parser:
            parser_method = getattr(self, config.custom_parser, None)
            if parser_method and callable(parser_method):
                self.logger.debug(f"Using custom parser: {config.custom_parser}")
                try:
                    yield from parser_method(response, config)
                except Exception as e:
                    self.logger.error(f"Custom parser failed: {e}", exc_info=True)
                return
            else:
                self.logger.warning(f"Custom parser '{config.custom_parser}' not found, using default")

        # Standard extraction with error handling
        try:
            # Extract title
            title = response.xpath(config.title_xpath).get()
            if not title:
                self.logger.warning(f"No title found for {response.url} using xpath: {config.title_xpath}")
                return
            title = title.strip()

            if not title:
                self.logger.warning(f"Empty title after strip for {response.url}")
                return

            # Extract tags
            tags = []
            if config.tags_xpath:
                try:
                    tags = response.xpath(config.tags_xpath).getall()
                    tags = [tag.strip() for tag in tags if tag.strip()]
                except Exception as e:
                    self.logger.warning(f"Failed to extract tags: {e}")

            # Extract author
            author = None
            if config.author_xpath:
                try:
                    author_result = response.xpath(config.author_xpath).get()
                    if author_result:
                        author = author_result.strip()
                except Exception as e:
                    self.logger.warning(f"Failed to extract author: {e}")

            # Extract post date
            post_date = None
            if config.post_date_xpath:
                try:
                    post_date_str = response.xpath(config.post_date_xpath).get()
                    if post_date_str and config.post_date_format:
                        try:
                            post_date = datetime.strptime(
                                post_date_str.strip(),
                                config.post_date_format
                            )
                        except ValueError as e:
                            self.logger.warning(
                                f"Failed to parse date '{post_date_str}' "
                                f"with format '{config.post_date_format}': {e}"
                            )
                except Exception as e:
                    self.logger.warning(f"Failed to extract post date: {e}")

            # Extract and clean body HTML
            body_html = response.xpath(config.body_xpath).get()

            if not body_html:
                self.logger.warning(f"No body content found for {response.url} using xpath: {config.body_xpath}")
                return

            cleaned_html = self.clean_html_fragment(body_html, config.exclude_xpaths)

            if not cleaned_html or len(cleaned_html.strip()) < 50:
                self.logger.warning(f"Body content too short after cleaning for {response.url}")
                return

            # Create and yield item
            yield ArticleItem(
                url=response.url,
                source_domain=domain,
                title=title,
                tags=tags,
                author=author,
                post_date=post_date,
                body=cleaned_html,
                body_type="html",
                lang=config.lang,
                timestamp=datetime.now()
            )

            self.logger.info(f"✓ Successfully scraped: {title[:50]}... from {domain}")

        except Exception as e:
            self.logger.error(
                f"Failed to parse {response.url}: {e}",
                exc_info=True
            )
            # Don't re-queue parsing errors - likely a config issue