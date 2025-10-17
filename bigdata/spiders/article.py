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

class ArticleSpider(RedisCrawlSpider):
    """
    Production-grade article spider with comprehensive error handling
    """

    name = 'article'
    redis_key = 'article:start_urls'

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

        # Create pagination rules for all domains
        for domain in all_domains:
            config = DomainConfigRegistry.get(domain)
            subdomain = config.site_subdomains or []
            domains = [domain, *subdomain] if subdomain else [domain]

            if not config.active:
                temp_logger.info(f"Skipping inactive domain: {domain}")
                continue

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

        # Create article extraction rules for all domains
        for domain in all_domains:
            config = DomainConfigRegistry.get(domain)
            subdomain = config.site_subdomains or []
            domains = [domain, *subdomain] if subdomain else [domain]

            if not config.active:
                continue

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
            request.meta['use_proxy']=True

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

    def parse_item(self, response):
        """Parse article using domain-specific configuration"""

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

        # Standard extraction with error handling
        try:

            title = response.xpath(config.title_xpath).get()
            if not title:
                self.logger.warning(
                    f"Possibly Not a content. No title found for {response.url} using xpath: {config.title_xpath}")
                return

            # check whether has matching body
            body_html = response.xpath(config.body_xpath).get()
            if not body_html:
                body_html = response.xpath('//body').get()
                if not body_html:
                    return
                else:
                    self.logger.warning(f"Using body as fallback, please check the content selector: {config.body_xpath}")

            # Extract title
            title = response.xpath(config.title_xpath).get()
            if not title:
                self.logger.warning(f"Possibly Not a content. No title found for {response.url} using xpath: {config.title_xpath}")
                return
            title = title.strip()

            if not title:
                self.logger.warning(f"Possibly Not a content. Empty title after strip for {response.url}")
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
            post_date_str = None
            if config.post_date_xpath:
                post_date_str = response.xpath(config.post_date_xpath).get()

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
                post_date=post_date_str,
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