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
    bypass_cf:bool = False
    link_extractors:dict = field(default_factory=dict)
    test_run: bool = False
    noises_xp :list[str] = field(default_factory=list[str])
    seeds:list[dict]=field(default_factory=list)
    xpath: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, dictionary:dict):

        cls(**dictionary)

    def to_dict(self) -> dict:
        return self.__dict__

class DailyLifeSpider(RedisCrawlSpider):

    name = 'daily_life'
    rules = []
    site_configs : dict[str, DomainConfig] = {}

    yielded: int = 0

    def on_yielded_count_change(self):
        pass

    def __init__(self, *args, **kwargs):
        settings = get_project_settings()
        domain_config_path = settings.get('SITE_CONFIG_PATH', 'site_config.json')
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
                # Merge with defaults
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
                rules.append(Rule(link_extractor=LxmlLinkExtractor(**ln),
                                  follow=True,
                                  process_request='_process_request_nav'))

            for la in config.link_extractors.get('articles',[]):
                rules.append(Rule(link_extractor=LxmlLinkExtractor(**la),
                                  callback='parse_article',
                                  process_request='_process_request'))

        self.rules = rules

    @staticmethod
    def get_domain(url):
        return urlparse(url).netloc.replace('www.', '')

    def _apply_domain_config(self, request, config):
        """Apply domain-specific configuration to request"""
        if config.bypass_cf:
            request.meta['bypass_cf'] = True
        if config.use_proxy:
            request.meta['use_proxy'] = True
        if config.test_run:
            request.meta['test_run'] = True
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

    def parse_article(self, response:Response):
        metadata = trafilatura.extract_metadata(response.text, default_url=response.url).as_dict()
        metadata['body_type'] = 'html'
        if cs := response.meta.get('content_subdomain'):
            metadata['content_subdomain']=cs
        yield CrawlItem(
            meta = metadata,
            body = response.text
        )
        self.yielded+=1
        self.on_yielded_count_change()