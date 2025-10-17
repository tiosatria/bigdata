import json
from datetime import datetime
from urllib.parse import urlparse
import random
import logging
import re
import os
from scrapy.http import Request
from scrapy.spiders import Rule
from scrapy_redis.spiders import RedisCrawlSpider
from scrapy.linkextractors import LinkExtractor
from scrapy.utils.project import get_project_settings
from bigdata.domain_configs import DomainConfigRegistry
from bigdata.domain_configs.domain_config import RenderEngine, CustomParser, OBVIOUS_EXCLUDES, blacklist_url_regex
from bigdata.items import ArticleItem
from lxml import etree, html
from bigdata.parsers.generic_auto import GenericAutoParser

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

        # Load generic dynamic settings
        settings = get_project_settings()

        # Apply dynamic domain hints from JSON (if configured / present) before generating rules
        try:
            hints_file = settings.get('DOMAIN_HINTS_FILE', None)
            if not hints_file:
                base_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
                hints_file = os.path.join(base_dir, 'domain_hints.json')
            hints_file = os.path.abspath(hints_file)
            _tmp_logger = logging.getLogger('article_spider')
            if os.path.exists(hints_file):
                with open(hints_file, 'r', encoding='utf-8') as f:
                    hints = json.load(f)
                DomainConfigRegistry.apply_dynamic_hints(hints)
                _tmp_logger.info(f"Applied dynamic domain hints from {hints_file}")
            else:
                _tmp_logger.debug(f"No dynamic hints file found at {hints_file}")
        except Exception as e:
            logging.getLogger('article_spider').error(f"Failed to load dynamic hints file: {e}", exc_info=True)

        allowed = settings.getlist('GENERIC_ALLOWED_DOMAINS') or settings.get('GENERIC_ALLOWED_DOMAINS', [])
        if isinstance(allowed, str):
            allowed = [x.strip() for x in allowed.split(',') if x.strip()]
        def _norm(d: str) -> str:
            try:
                from urllib.parse import urlparse
                d = (d or "").strip().lower()
                if not d:
                    return ""
                p = urlparse(d)
                host = (p.netloc or d).strip("/")
                if not host and p.path:
                    host = p.path.strip("/")
                return host.replace("www.", "")
            except Exception:
                return d.replace("www.", "").strip().lower().strip("/")
        self.generic_allowed_domains = set(filter(None, (_norm(d) for d in allowed)))
        self.generic_min_body_chars = int(settings.getint('GENERIC_MIN_BODY_CHARS', 200))
        self.generic_parser = GenericAutoParser(min_body_chars=self.generic_min_body_chars)
        self.generic_article_url_patterns = GenericAutoParser.DEFAULT_ARTICLE_URL_PATTERNS
        self.generic_deny_patterns = list(blacklist_url_regex) + list(GenericAutoParser.DEFAULT_DENY_PATTERNS)

        # Generate rules before spider initialization
        self._generate_rules()

        # Now initialize parent
        super().__init__(*args, **kwargs)

        # Now self.logger is available
        self.logger.info(f"Spider initialized with {len(self.rules)} rules (configs: {len(DomainConfigRegistry.get_all_domains())}, generic domains: {len(self.generic_allowed_domains)})")

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
                            allow=(config.allowed_url_regex or None),
                            deny=(config.deny_urls_regex + (config.blocked_url_keywords or []))
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
                            allow=(config.allowed_url_regex or None),
                            deny=(config.deny_urls_regex + (config.blocked_url_keywords or []))
                        ),
                        callback='parse_item',
                        follow=config.follow_related_content,
                        process_request='_process_request',
                    )
                )
                temp_logger.debug(f"Added article rule for {domain}")

        # Add generic dynamic rules if configured
        if getattr(self, 'generic_allowed_domains', None):
            gad = list(self.generic_allowed_domains)

            # 1) Targeted parse rule for likely article URLs (first priority)
            rules.append(
                Rule(
                    LinkExtractor(
                        allow_domains=gad,
                        allow=self.generic_article_url_patterns,
                        deny=self.generic_deny_patterns
                    ),
                    callback='parse_item',
                    follow=True,
                    process_request='_process_request'
                )
            )

            # 2) Fallback: attempt parse on all pages within allowed domains (high recall, low FP via parser heuristics)
            rules.append(
                Rule(
                    LinkExtractor(
                        allow_domains=gad,
                        deny=self.generic_deny_patterns
                    ),
                    callback='parse_item',
                    follow=True,
                    process_request='_process_request'
                )
            )

            # 3) Broad follow rule (no callback) placed last as safety for discovery
            rules.append(
                Rule(
                    LinkExtractor(
                        allow_domains=gad,
                        deny=self.generic_deny_patterns
                    ),
                    follow=True,
                    process_request='_process_request'
                )
            )

            temp_logger.info(f"Added generic rules for {len(gad)} domain(s)")

        self.rules = tuple(rules)
        temp_logger.info(f"Generated {len(self.rules)} rules total")

    @staticmethod
    def get_domain(url):
        return urlparse(url).netloc.replace('www.', '')

    def _process_request(self, request, response):
        domain = self.get_domain(request.url)
        config = DomainConfigRegistry.get(domain)
        if not config:
            # Allow if domain is explicitly allowed for generic mode (including subdomains)
            if getattr(self, 'generic_allowed_domains', None):
                for gad in self.generic_allowed_domains:
                    if domain == gad or domain.endswith('.' + gad):
                        request.meta['domain'] = domain
                        return request
            self.logger.warning(f"No config for {domain}, dropping")
            return None

        # Apply domain allow/deny guards before making the request
        try:
            url_l = (request.url or "").lower()
            # Keyword-based URL blocking
            if getattr(config, 'blocked_url_keywords', None):
                for kw in config.blocked_url_keywords:
                    if kw and kw in url_l:
                        self.logger.debug(f"Dropping by blocked_url_keywords '{kw}': {request.url}")
                        return None
            # Regex allow-list (categories): if provided, require a match
            if getattr(config, 'allowed_url_regex', None):
                allowed_match = False
                for pat in config.allowed_url_regex:
                    try:
                        if re.search(pat, request.url):
                            allowed_match = True
                            break
                    except re.error:
                        # If bad regex, skip silently
                        continue
                if not allowed_match:
                    self.logger.debug(f"Dropping by allowed_url_regex (no match): {request.url}")
                    return None
            # Explicit deny regex as last guard (redundant to LinkExtractor but safe)
            if getattr(config, 'deny_urls_regex', None):
                for pat in config.deny_urls_regex:
                    try:
                        if re.search(pat, request.url):
                            self.logger.debug(f"Dropping by deny_urls_regex '{pat}': {request.url}")
                            return None
                    except re.error:
                        continue
        except Exception:
            pass

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
        """Parse article using domain-specific configuration with generic fallback"""

        # Identify domain from URL
        domain = urlparse(response.url).netloc.replace('www.', '').replace(":80", "").replace(":443", "")
        config = DomainConfigRegistry.get(domain)

        # If no config, try generic parser for allowed domains
        if not config:
            if getattr(self, 'generic_allowed_domains', None) and domain in self.generic_allowed_domains:
                try:
                    yield from self.generic_parser.parse_item(response, None, self)
                except Exception as e:
                    self.logger.error(f"Generic parser failed: {e}", exc_info=True)
            else:
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
                # Fallback to generic detection
                if getattr(self, 'generic_parser', None):
                    yield from self.generic_parser.parse_item(response, None, self)
                return

            # check whether has matching body
            body_html = response.xpath(config.body_xpath).get()
            if not body_html:
                body_html = response.xpath('//body').get()
                if not body_html:
                    # Fallback to generic detection
                    if getattr(self, 'generic_parser', None):
                        yield from self.generic_parser.parse_item(response, None, self)
                    return
                else:
                    self.logger.warning(f"Using body as fallback, please check the content selector: {config.body_xpath}")

            # Extract title
            title = response.xpath(config.title_xpath).get()
            if not title:
                self.logger.warning(f"Possibly Not a content. No title found for {response.url} using xpath: {config.title_xpath}")
                # Fallback to generic detection
                if getattr(self, 'generic_parser', None):
                    yield from self.generic_parser.parse_item(response, None, self)
                return
            title = title.strip()

            if not title:
                self.logger.warning(f"Possibly Not a content. Empty title after strip for {response.url}")
                # Fallback to generic detection
                if getattr(self, 'generic_parser', None):
                    yield from self.generic_parser.parse_item(response, None, self)
                return

            # Title-based blocking hints
            try:
                if getattr(config, 'blocked_title_keywords', None):
                    t_l = title.lower()
                    for kw in config.blocked_title_keywords:
                        if kw and kw in t_l:
                            self.logger.debug(f"Dropping by blocked_title_keywords '{kw}': {response.url}")
                            return
            except Exception:
                pass

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
                # Fallback to generic detection
                if getattr(self, 'generic_parser', None):
                    yield from self.generic_parser.parse_item(response, None, self)
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

    def parse_start_url(self, response):
        """Attempt parsing on start URLs as well (generic mode will filter non-articles)."""
        yield from self.parse_item(response)
