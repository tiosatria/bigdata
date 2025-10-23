from dataclasses import dataclass, field
from urllib.parse import urlparse
from scrapy.exceptions import IgnoreRequest, CloseSpider
from scrapy.utils.project import get_project_settings
from scrapy_redis.spiders import RedisCrawlSpider
from scrapy.responsetypes import Response
import os
import json
from scrapy.spiders import Rule
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
import trafilatura
from bigdata.items import CrawlItem
from redis import Redis
import re

NAVIGATION_REGEX : list[re.Pattern[str]] = [
        re.compile(r"(?:/)?(?:category|categories)(?:/|$)", re.IGNORECASE),
        re.compile(r"(?:/)?(index)(?:/|$)", re.IGNORECASE),
        re.compile(r"(?:/)?(?:tag|tags)(?:/|$)", re.IGNORECASE),
        re.compile(r"(?:/)?(?:author|authors|user|users)(?:/|$)", re.IGNORECASE),
        re.compile(r"(?:/)?(?:page|pages|p)(?:/|$)?\d*", re.IGNORECASE),
        re.compile(r"(?:/)?(?:search|s|query|find)(?:/|$)", re.IGNORECASE),
        re.compile(r"(?:/)?(?:archive|archives|posts|list)(?:/|$)", re.IGNORECASE),
        re.compile(r"(?:/)?(?:feed|rss|atom)(?:/|$)", re.IGNORECASE),
        re.compile(r"(?:/)?(?:comment|comments|responses)(?:/|$)", re.IGNORECASE),
        re.compile(r"(?:/)?(?:wp-json|wp-admin|wp-content|xmlrpc\.php)(?:/|$)", re.IGNORECASE),
        re.compile(r"(?:/)?(?:login|logout|signup|register|account|profile)(?:/|$)?", re.IGNORECASE),
        re.compile(r"(?:/)?(?:api|static|assets|uploads|media)(?:/|$)", re.IGNORECASE),
    re.compile(r"(?:/)?(?:about-us|sitemap|faqs|our-impact|authors|podcasts)(?:/|$)", re.IGNORECASE),
]

COMMON_DENY_REGEX : list[re.Pattern[str]] = [
    # WordPress admin and technical endpoints
    re.compile(r"^(?:/)?(?:wp-json|wp-admin|wp-includes|xmlrpc\.php)(?:/|$)", re.IGNORECASE),
    # Authentication and user account pages
    re.compile(
        r"(?:/)?(?:login|logout|signin|signout|sign-in|sign-out|signup|sign-up|register|auth|authentication|newsletter|product|shop|my-account)(?:/|$)?",
        re.IGNORECASE),
    re.compile(r"(?:/)?(?:account|profile|dashboard|settings|preferences|my-account|user)(?:/|$)", re.IGNORECASE),
    # API endpoints (but not content APIs)
    re.compile(r"(?:/)?api/(?:v\d+/)?(?:auth|user|admin|config)", re.IGNORECASE),
    # Static assets and media files (not pages)
    re.compile(r"\.(css|js|json|xml|txt|pdf|zip|tar|gz|rar|exe|dmg|iso)$", re.IGNORECASE),
    re.compile(r"\.(jpg|jpeg|png|gif|svg|ico|webp|bmp|tiff|mp4|avi|mov|mp3|wav|woff|woff2|ttf|eot)$", re.IGNORECASE),
    # Feed and technical formats
    re.compile(r"(?:/)?(?:feed|rss|atom|sitemap)(?:/|\.xml|$)", re.IGNORECASE),
    # Search and filter URLs (usually dynamic, not unique content)
    re.compile(r"[?&](?:s|search|q|query|filter|sort|order|page|p)=", re.IGNORECASE),
    # Comments, replies, and action URLs
    re.compile(r"(?:/)?(?:comment|reply|replytocom)(?:/|$|\?)", re.IGNORECASE),
    re.compile(r"[?&]replytocom=", re.IGNORECASE),
    # Share and redirect URLs
    re.compile(r"(?:/)?(?:share|redirect|goto|track|click)(?:/|$|\?)", re.IGNORECASE),
    # Cart, checkout, and e-commerce
    re.compile(r"(?:/)?(?:cart|checkout|basket|wishlist|compare)(?:/|$)?", re.IGNORECASE),
    # Duplicate content with tracking parameters
    re.compile(r"[?&](?:utm_|fbclid|gclid|ref=|source=)", re.IGNORECASE),
re.compile(r"/(?:about-us|sitemap|faqs|our-impact|authors|podcasts|about)(?:/|$)?", re.IGNORECASE),
    re.compile(r"/(?:terms-and-conditions|privacy|privacy-policy|servicesandsupport|contact|accessibility)(?:/|$)?", re.IGNORECASE),
    re.compile(r".*comment.*")
]

@dataclass
class DomainConfig:

    domain:str
    delivery_version = 'v1'
    lang:str = 'en'
    type:str = 'article'
    content_domain:str = 'general'
    content_subdomain:str = 'living'
    active:bool = True
    use_proxy:bool= True
    use_playwright:bool = False
    bypass_cf:bool = False
    link_extractors:dict = field(default_factory=dict)
    test_run: bool = False
    push_seed:bool = False
    noises_xp :list[str] = field(default_factory=list[str])
    seeds:list[dict]=field(default_factory=list)
    xpath: dict = field(default_factory=dict)

    # todo : append navigation regex to compiled_re
    compiled_re:dict = field(default_factory=dict)
    compiled_body_signatures:list = field(default_factory=list)

    def __post_init__(self):
        obvious_deny = COMMON_DENY_REGEX.copy()
        if self.link_extractors:
            re_compiles = []
            for nav_signature_re in self.compiled_re.get('navigation_signature', []):
                reg = re.compile(nav_signature_re)
                re_compiles.append(reg)
            self.compiled_re['navigation_signature'] = re_compiles

            for le in self.link_extractors.get('follow_and_parse', []):
                for deny in le.get('deny',[]):
                    obvious_deny.append(re.compile(deny))
                le['deny'] = obvious_deny

    @classmethod
    def from_dict(cls, dictionary:dict):
        cls(**dictionary)

    def to_dict(self) -> dict:
        return self.__dict__

class DailyLifeSpider(RedisCrawlSpider):

    name = 'dailylife'

    rules = []

    site_configs : dict[str, DomainConfig] = {}

    yielded: int = 0

    def push_seed(self) -> int:
        server: Redis = self.server
        seeded = 0
        if not server:
            raise CloseSpider('unable to push seed, please check redis connection')
        for domain, config in self.site_configs.items():
            self.logger.debug(f'Attempting to push seed for domain: {domain}')
            if not config.active or (not config.test_run and not config.push_seed):
                continue
            for seed in config.seeds:
                if isinstance(seed,str):
                    server.lpush(f"{self.name}:start_urls", seed)
                    continue
                if url:=seed.get('url'):
                    self.logger.info(f'pushed 1 seed with url {url}. for domain: {domain}')
                    server.rpush(f"{self.name}:start_urls", json.dumps(seed))
                    seeded+=1
        return seeded

    def start_requests(self):
        self.push_seed()
        return super().start_requests()

    def __init__(self, *args, **kwargs):
        settings = get_project_settings()
        domain_config_path = settings.get('SITE_CONFIG_PATH', 'site_cfg.json')
        self.load_config(domain_config_path)
        self._generate_rules()
        super().__init__(*args, **kwargs)
        self.logger.info(f"Spider initialized with {len(self.rules)} rules. and {len(self.site_configs)}")

    def load_config(self, config_path):
        if not os.path.exists(config_path):
            self.logger.warning(f"sites config not found: {config_path}")
            raise CloseSpider('no_config')
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                site_configs = json.load(f)
            domains = site_configs.get('domains', {})
            self.logger.info(f"Loading {len(domains)} wild crawl domains from {config_path}")
            for domain_spec in domains:
                cfg = DomainConfig(**domain_spec)
                self.site_configs[cfg.domain] = cfg
                self.logger.info(f'Registered site config for {cfg.domain}')
        except Exception as e:
            self.logger.error(f"Failed to load wild crawl config: {e}", exc_info=True)

    def _generate_rules(self):
        rules = []
        for domain, config in self.site_configs.items():
            if not config.active:
                self.logger.info(f"Skipping inactive domain: {domain}")
                continue

            for ln in config.link_extractors.get('navs',[]):
                rules.append(Rule(link_extractor=LxmlLinkExtractor(
                    allow_domains=domain,
                    **ln),
                                  follow=True,
                                  process_request='_process_request_nav'))

            for la in config.link_extractors.get('articles',[]):
                rules.append(Rule(link_extractor=LxmlLinkExtractor(
                    allow_domains=domain,
                    **la),
                                  callback='parse_article',
                                  process_request='_process_request'))

            for fap in config.link_extractors.get('follow_and_parse',[]):
                fap_rule = Rule(link_extractor=LxmlLinkExtractor(
                    allow_domains=domain,
                    **fap),
                    callback='follow_and_parse',
                    follow=True,
                    process_request='_process_follow_and_parse_request')
                rules.append(fap_rule)
                for denies in fap.get('deny',[]):
                    print(f'denies regex: {denies}')

        self.rules = rules

    @staticmethod
    def get_domain(url):
        return urlparse(url).netloc.replace('www.', '')

    def apply_playwright_meta(self, request, config):
        request.meta['playwright'] = True
        request.meta['playwright_page_goto_kwargs'] = {
            'wait_until': 'domcontentloaded',
        }

    def _apply_domain_config(self, request, config):
        """Apply domain-specific configuration to request"""
        if config.bypass_cf:
            request.meta['bypass_cf'] = True
        if config.use_proxy:
            request.meta['use_proxy'] = True
        if config.test_run:
            request.meta['test_run'] = True
        if config.use_playwright:
            self.apply_playwright_meta(request,config)
        return request

    def _process_request_nav(self, request, response):
        request.meta['is_nav'] = True
        return self._process_request(request, response)

    def _process_request(self, request, response):
        domain = self.get_domain(request.url)
        config = self.site_configs.get(domain)
        if not config:
            self.logger.warning(f"No config for {domain}, dropping and will not be considered in the future.")
            raise IgnoreRequest
        request.meta['domain'] = domain
        self._apply_domain_config(request, config)
        return request

    def _process_follow_and_parse_request(self, request, response):
        req = self._process_request(request,response)
        req.meta['from_follow_and_parse']= True
        return req

    def get_and_set_metadata(self, response:Response):
        metadata = (trafilatura
                    .extract_metadata(response.text,
                                      default_url=response.url)
                    .as_dict())
        metadata['body_type'] = 'html'
        if cs := response.meta.get('content_subdomain'):
            metadata['content_subdomain'] = cs
        if cd := response.meta.get('content_domain'):
            metadata['content_domain'] = cd
        return metadata

    # todo : respect navigation regex inside domain config
    def is_navigation_link(self,response:Response, config) -> bool:
        # check whether the response has index match
        for regx in NAVIGATION_REGEX:
            match = bool(re.Pattern.match(regx, response.url))
            self.logger.debug(f'is_nav_link: {match}')
            return match
        self.logger.debug(f'is_nav_link: False')
        return False

    def follow_and_parse(self, response:Response):
        self.logger.debug(f'Parsing response from {response.url}')
        config = self.site_configs.get(response.meta['domain'])
        is_nav = self.is_navigation_link(response, config)
        if is_nav:
            self.logger.debug('is navigation link, skipping parsing')
            return

        metadata = self.get_and_set_metadata(response)

        self.logger.debug(f'metadata: {metadata}')

        body = None
        # check whether has body declared
        for body_signature in config.compiled_body_signatures:
            if response.xpath(body_signature):
                body = response.xpath(body_signature).get()
                self.logger.debug(f'found body signature: {body_signature}')
                break

        if not metadata:
            self.logger.debug('no metadata found, parsing skipped')
            return

        if not body:
            self.logger.debug('content signature not detected, yielding full html')

        yield CrawlItem(
            meta = metadata,
            body = body or response.text
        )

        self.yielded+=1
        self.logger.info(f'Yielded {metadata.get("title")} on : {response.url}. Total yielded: {self.yielded}')

    def parse_article(self, response:Response):
        metadata= self.get_and_set_metadata(response)
        bx = self.site_configs.get(response.meta['domain']).xpath.get('body')
        body = response.xpath(bx).get() if bx else response.text
        if not body:
            self.logger.debug('no body xpath container were found, falling back to raw body')
            body = response.text
        yield CrawlItem(
            meta = metadata,
            body = body
        )
        self.yielded+=1
        self.logger.info(f'Yielded {metadata.get('title')} on : {response.url}')

