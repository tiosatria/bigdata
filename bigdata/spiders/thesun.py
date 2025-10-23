from redis import Redis
from scrapy.exceptions import CloseSpider
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor

from bigdata.middlewares import ProxyMiddleware, FailedRequestExportMiddleware
from bigdata.spiders.dailylifespider import DailyLifeSpider, DomainConfig
from scrapy.spiders import Rule
import json

CFG: dict = {
    "domain": "thesun.co.uk",
    "active": True,
    "bypass_cf": True,
    "seeds": [
        # {
        #     "url": r"https://www.thesun.co.uk/health/page/24",
        #     "meta": {
        #         # "playwright": True,
        #         'bypass_cf': True
        #     }
        # },
        {
            "url": r"https://www.thesun.co.uk/money/tips/page/24",
            "meta": {
                # "playwright": True
                'bypass_cf': True
            }
        }, {
            "url": r"https://www.thesun.co.uk/topic/sun-savers/page/24",
            "meta": {
                # "playwright": True
                'bypass_cf': True
            }
        }
    ],
    "link_extractors": {
        "articles": [
            {
                "restrict_xpaths": [
                    "//div[contains(@class,'layout__item')]//div[@class='story__copy-container']/a"
                ]
            }
        ],
        "navs": [
            {
                "restrict_xpaths": [
                    "//a[@class='pagination__item pagination__item--directional pagination__item--next']"
                ]
            }
        ]
    },
    "push_seed": True,
    "test_run": False
}


class TheSunSpider(DailyLifeSpider):
    name = 'thesun'
    allowed_domains = ['thesun.co.uk']

    custom_settings = {
        'CONCURRENT_REQUESTS': 120,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 24,
        'DOWNLOAD_DELAY': 0,
        'LOG_LEVEL': 'DEBUG',
        'COMPRESSION_ENABLED': False,
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': None,
            ProxyMiddleware: 350,
            'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 400,
            'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 500,
            FailedRequestExportMiddleware: 543
        },
        'REFERER_ENABLED': True
    }

    seeds = CFG['seeds']
    config = DomainConfig(**CFG)

    def _generate_rules(self):
        self.site_configs = {
            'thesun.co.uk': self.config
        }

    rules = [
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=[
                "//div[contains(@class,'layout__item')]//div[@class='story__copy-container']/a"
            ]
        ), callback='parse_article',
            process_request='_process_request'
        ),
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=[
                "//a[@class='pagination__item pagination__item--directional pagination__item--next']"
            ]
        ), follow=True, process_request='_process_request_nav')
    ]

    def parse_start_url(self, response, **kwargs):
        print(f'{response.text}')
        super().parse_start_url(response)

    def push_seed(self) -> int:
        server: Redis = self.server
        if not server:
            raise CloseSpider('unable to push seed, please check redis connection')
        for seed in self.seeds:
            if isinstance(seed, str):
                server.lpush(f"{self.name}:start_urls", seed)
            if url := seed.get('url'):
                self.logger.info(f'pushed 1 seed with url {url}.')
                server.lpush(f"{self.name}:start_urls", json.dumps(seed))
        return len(self.seeds)

    def _apply_domain_config(self, request, config):
        super()._apply_domain_config(request, self.config)
        # self.apply_playwright_meta(request, config)
        return request
