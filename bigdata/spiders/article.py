import json
from datetime import datetime
from urllib.parse import urlparse
import random
import logging
from scrapy.spiders import Rule
from scrapy_redis.spiders import RedisCrawlSpider
from scrapy.linkextractors import LinkExtractor
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

            if config.navigation_xpaths:
                rules.append(
                    Rule(
                        LinkExtractor(
                            allow_domains=[domain],
                            restrict_xpaths=config.navigation_xpaths
                        ),
                        follow=True,
                        process_request='_process_request',
                    )
                )
                temp_logger.debug(f"Added pagination rule for {domain}")

        # Create article extraction rules for all domains
        for domain in all_domains:
            config = DomainConfigRegistry.get(domain)

            if not config.active:
                continue

            if config.article_target_xpaths:
                rules.append(
                    Rule(
                        LinkExtractor(
                            allow_domains=[domain],
                            restrict_xpaths=config.article_target_xpaths
                        ),
                        callback='parse_item',
                        follow=True,
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
        """Process pagination requests with depth tracking"""
        domain = self.get_domain(request.url)
        config = DomainConfigRegistry.get(domain)
        if not config:
            self.logger.warning(f"No config for {domain}, using defaults")
            return request
        # Apply configuration
        request = self._apply_domain_config(request, config)
        request.meta['domain'] = domain
        return request

    def _apply_domain_config(self, request, config):
        """Apply domain-specific configuration to request"""
        if config.render_engine == RenderEngine.PLAYWRIGHT:
            request.meta['playwright'] = True
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
            post_date_str = None
            if config.post_date_xpath:
                post_date_str = response.xpath(config.post_date_xpath).get()
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
            # Don't re-queue parsing errors - likely a config issue

    def parse_bonappetit(self, response, config):
        title = None
        tags = []
        author = None
        post_date = None
        json_obj = {}  # Initialize to avoid UnboundLocalError in the yield statement

        try:
            # The XPath should select the text content of the script tag
            json_string = response.xpath(config.body_xpath).get()
            json_obj = json.loads(json_string)

            title = json_obj.get("headline")  # "headline" is more specific than "name" or "title"
            tags = json_obj.get("keywords", [])  # .get() with a default value is safer

            # Author is a list of objects, so we access the first item's 'name'
            author_list = json_obj.get("author", [])
            if author_list:
                author = author_list[0].get("name")

            post_date = json_obj.get("datePublished")

        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            self.logger.error(f"Failed to parse JSON from {response.url}. Error: {e}")

        self.logger.info(f"✓ Successfully scraped: {title[:50]}... from {config.domain}")

        yield ArticleItem(
            url=response.url,
            source_domain=config.domain,
            title=title,
            tags=tags,
            author=author,
            post_date=post_date,
            body=json_obj,
            body_type="json",
            lang=config.lang,
            timestamp=datetime.now()
        )