import json
from datetime import datetime
from urllib.parse import urlparse
import random
import logging
import re
from scrapy.http import Request
from scrapy.spiders import Rule
from scrapy_redis.spiders import RedisCrawlSpider
from scrapy.linkextractors import LinkExtractor
from bigdata.domain_configs import DomainConfigRegistry
from bigdata.domain_configs.domain_config import RenderEngine, CustomParser
from bigdata.items import ArticleItem
from lxml import etree, html

# Import trafilatura for content extraction
try:
    import trafilatura
    from trafilatura.settings import use_config

    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    logging.warning("trafilatura not installed. Wild crawl mode will be limited.")


class ArticleSpider(RedisCrawlSpider):
    """
    Production-grade article spider with comprehensive error handling
    Supports both XPath-based (precise) and trafilatura-based (wild crawl) extraction
    """

    name = 'article'
    redis_key = 'article:start_urls'

    # Rules will be generated dynamically
    rules = ()

    def __init__(self, *args, **kwargs):
        # Get wild crawl config path from settings
        from scrapy.utils.project import get_project_settings
        settings = get_project_settings()
        wild_crawl_path = settings.get('WILD_CRAWL_CONFIG_PATH')

        # Load domain configurations BEFORE calling super().__init__
        DomainConfigRegistry.load_all_configs(wild_crawl_config_path=wild_crawl_path)

        # Configure trafilatura for optimal extraction
        if TRAFILATURA_AVAILABLE:
            self.trafilatura_config = use_config()
            self.trafilatura_config.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")

        # Generate rules before spider initialization
        self._generate_rules()

        # Now initialize parent
        super().__init__(*args, **kwargs)

        # Now self.logger is available
        self.logger.info(f"Spider initialized with {len(self.rules)} rules")
        if TRAFILATURA_AVAILABLE:
            self.logger.info("Trafilatura extraction enabled")

    def _generate_rules(self):
        """Generate crawling rules from all registered domain configs"""
        rules = []
        all_domains = DomainConfigRegistry.get_all_domains()

        # Use a temporary logger since self.logger isn't available yet
        temp_logger = logging.getLogger('article_spider')
        temp_logger.info(f"Generating rules for {len(all_domains)} domains")

        def sanitize_xpaths(xpaths, domain, purpose):
            if not xpaths:
                return []
            entries = xpaths if isinstance(xpaths, (list, tuple)) else [xpaths]
            valid = []
            for xp in entries:
                if not xp or not isinstance(xp, str):
                    continue
                try:
                    etree.XPath(xp)
                    valid.append(xp)
                except Exception as e:
                    temp_logger.warning(f"Skipping invalid XPath for {domain} ({purpose}): {xp} -> {e}")
            return valid

        # Process each domain
        for domain in all_domains:
            config = DomainConfigRegistry.get(domain)
            subdomain = config.site_subdomains or []
            domains = [domain, *subdomain] if subdomain else [domain]

            if not config.active:
                temp_logger.info(f"Skipping inactive domain: {domain}")
                continue

            # WILD CRAWL MODE: Use generic link extraction
            if config.is_wild_crawl:
                temp_logger.info(f"Creating wild crawl rules for {domain}")

                # Rule 1: Follow ALL internal links (no XPath restriction)
                # This crawls the entire site
                rules.append(
                    Rule(
                        LinkExtractor(
                            allow_domains=domains,
                            deny=config.deny_urls_regex,
                            # No restrict_xpaths - follow everything
                        ),
                        callback='parse_item',
                        follow=True,  # Keep crawling deeper
                        process_request='_process_request',
                    )
                )
                temp_logger.debug(f"Added wild crawl rule for {domain}")
                continue

            # CONFIGURED MODE: Use precise XPath-based extraction
            nav_xps = sanitize_xpaths(config.navigation_xpaths, domain, 'navigation')
            if nav_xps:
                rules.append(
                    Rule(
                        LinkExtractor(
                            allow_domains=domains,
                            restrict_xpaths=nav_xps,
                            deny=config.deny_urls_regex
                        ),
                        follow=True,
                        process_request='_process_request',
                    )
                )
                temp_logger.debug(f"Added pagination rule for {domain}")

            article_xps = sanitize_xpaths(config.article_target_xpaths, domain, 'article_targets')
            if article_xps:
                rules.append(
                    Rule(
                        LinkExtractor(
                            allow_domains=domains,
                            restrict_xpaths=article_xps,
                            deny=config.deny_urls_regex
                        ),
                        callback='parse_item',
                        follow=config.follow_related_content,
                        process_request='_process_request',
                    )
                )
                temp_logger.debug(f"Added article rule for {domain}")

        self.rules = tuple(rules)
        temp_logger.info(f"Generated {len(self.rules)} rules total")

    @staticmethod
    def get_domain(url):
        return urlparse(url).netloc.replace('www.', '')

    def _process_request(self, request, response):
        domain = self.get_domain(request.url)
        config = DomainConfigRegistry.get(domain)
        if not config:
            self.logger.warning(f"No config for {domain}, dropping")
            return None

        # Apply configuration
        request = self._apply_domain_config(request, config)
        request.meta['domain'] = domain

        return request

    def _apply_domain_config(self, request, config):
        """Apply domain-specific configuration to request"""
        if config.render_engine == RenderEngine.PLAYWRIGHT:
            request.meta['playwright'] = True
        if config.cloudflare_proxy_bypass:
            request.meta['cf-bypass'] = True
        if config.use_proxy:
            request.meta['use_proxy'] = True

        return request

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

    def extract_with_trafilatura(self, response, config):
        """
        Extract content using trafilatura
        Returns dict with extracted fields or None if extraction fails

        Process:
        1. Pre-clean raw HTML (remove OBVIOUS_EXCLUDES bloat)
        2. Trafilatura extracts main article content
        3. Return extracted article HTML + clean text
        """
        if not TRAFILATURA_AVAILABLE:
            self.logger.warning("Trafilatura not available")
            return None

        try:
            # STEP 1: Pre-clean raw HTML to remove bloat before trafilatura processing
            # This reduces processing time and prevents bloat in extracted content
            precleaned_html = self.clean_html_fragment(response.text, config.exclude_xpaths)

            if not precleaned_html:
                self.logger.debug(f"HTML empty after pre-cleaning for {response.url}")
                return None

            # STEP 2: Extract main article HTML using trafilatura
            article_html = trafilatura.extract(
                precleaned_html,
                include_images=True,
                include_tables=True,
                include_formatting=True,
                include_links=False,
                output_format='html',  # Get clean article HTML
                config=self.trafilatura_config
            )

            if not article_html:
                self.logger.debug(f"Trafilatura returned no content for {response.url}")
                return None

            # STEP 3: Extract clean text content (for body_content field)
            body_content = trafilatura.extract(
                precleaned_html,
                include_images=True,
                include_tables=True,
                include_formatting=True,
                include_links=False,
                output_format='txt',
                config=self.trafilatura_config
            )

            # STEP 4: Get metadata
            metadata = trafilatura.extract_metadata(precleaned_html)

            # Extract title
            title = None
            if metadata and metadata.title:
                title = metadata.title

            # Fallback: try from article HTML
            if not title:
                try:
                    doc = html.fromstring(article_html)
                    h1_text = doc.xpath('//h1//text()')
                    if h1_text:
                        title = ' '.join(h1_text).strip()
                except:
                    pass

            # Final fallback: from original response
            if not title:
                h1 = response.xpath('//h1//text()').get()
                if h1:
                    title = h1.strip()

            if not title:
                self.logger.debug(f"No title extracted for {response.url}")
                return None

            # Validate content length
            if len(article_html.strip()) < 100:
                self.logger.debug(f"Article HTML too short ({len(article_html)} chars) for {response.url}")
                return None

            # Extract other metadata
            author = metadata.author if metadata else None
            post_date = metadata.date if metadata else None
            tags = metadata.categories if metadata else []
            if tags and isinstance(tags, str):
                tags = [t.strip() for t in tags.split(',')]

            return {
                'title': title,
                'author': author,
                'post_date': post_date,
                'tags': tags or [],
                'body': article_html,  # Trafilatura-extracted article HTML (main content only)
                'body_content': body_content,  # Trafilatura cleaned text with formatting
                'extraction_method': 'trafilatura'
            }

        except Exception as e:
            self.logger.error(f"Trafilatura extraction failed for {response.url}: {e}", exc_info=True)
            return None

    def extract_with_xpath(self, response, config):
        """
        Extract content using XPath (original method)
        Returns dict with extracted fields or None if extraction fails
        """
        try:
            # Extract title
            title = response.xpath(config.title_xpath).get()
            if not title:
                self.logger.warning(
                    f"No title found for {response.url} using xpath: {config.title_xpath}")
                return None
            title = title.strip()

            if not title:
                self.logger.warning(f"Empty title after strip for {response.url}")
                return None

            # Extract body
            body_html = response.xpath(config.body_xpath).get()
            if not body_html:
                body_html = response.xpath('//body').get()
                if not body_html:
                    return None
                else:
                    self.logger.warning(f"Using body as fallback for {config.body_xpath}")

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
            post_date_str = None
            if config.post_date_xpath:
                post_date_str = response.xpath(config.post_date_xpath).get()

            # Clean HTML
            cleaned_html = self.clean_html_fragment(body_html, config.exclude_xpaths)

            if not cleaned_html or len(cleaned_html.strip()) < 50:
                self.logger.warning(f"Body content too short after cleaning for {response.url}")
                return None

            # Extract text content for body_content (strip HTML tags)
            try:
                doc = html.fromstring(cleaned_html)
                body_text = doc.text_content()
            except:
                body_text = cleaned_html

            return {
                'title': title,
                'author': author,
                'post_date': post_date_str,
                'tags': tags,
                'body': cleaned_html,
                'body_content': body_text,
                'extraction_method': 'xpath'
            }

        except Exception as e:
            self.logger.error(f"XPath extraction failed for {response.url}: {e}")
            return None

    def parse_item(self, response):
        """Parse article using domain-specific configuration or trafilatura"""

        # Identify domain from URL
        domain = urlparse(response.url).netloc.replace('www.', '')
        config = DomainConfigRegistry.get(domain)

        if not config:
            self.logger.warning(f"No config found for domain: {domain}")
            return

        # Use custom parser if specified
        if config.custom_parser and isinstance(config.custom_parser, CustomParser):
            try:
                yield from config.custom_parser.parse_item(response, config, self)
            except Exception as e:
                self.logger.error(f"Custom parser failed: {e}", exc_info=True)
            return

        extracted_data = None

        # WILD CRAWL MODE: Use trafilatura primarily
        if config.is_wild_crawl:
            extracted_data = self.extract_with_trafilatura(response, config)

            if not extracted_data:
                self.logger.debug(f"Trafilatura failed for {response.url}, skipping")
                return

        # CONFIGURED MODE: Use XPath, fallback to trafilatura
        else:
            extracted_data = self.extract_with_xpath(response, config)

            # Fallback to trafilatura if XPath fails
            if not extracted_data and TRAFILATURA_AVAILABLE:
                self.logger.info(f"XPath extraction failed, trying trafilatura for {response.url}")
                extracted_data = self.extract_with_trafilatura(response, config)
                if extracted_data:
                    extracted_data['extraction_method'] = 'hybrid'

        if not extracted_data:
            self.logger.warning(f"All extraction methods failed for {response.url}")
            return

        # Create and yield item
        yield ArticleItem(
            url=response.url,
            source_domain=domain,
            title=extracted_data['title'],
            tags=extracted_data.get('tags', []),
            author=extracted_data.get('author'),
            post_date=extracted_data.get('post_date'),
            body=extracted_data['body'],
            body_type="html",
            body_content=extracted_data.get('body_content'),
            extraction_method=extracted_data['extraction_method'],
            lang=config.lang,
            timestamp=datetime.now()
        )

        self.logger.info(
            f"✓ Successfully scraped [{extracted_data['extraction_method']}]: "
            f"{extracted_data['title'][:50]}... from {domain}"
        )