from redis import Redis
from scrapy.exceptions import CloseSpider
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor

from bigdata.spiders.dailylifespider import DailyLifeSpider, DomainConfig
from scrapy.spiders import Rule
import json

from bigdata.spiders.guardian import GuardianSpider

CFG = {
    "domain": "telegraph.co.uk",
    "active": True,
    "use_playwright": True,
    "link_extractors": {
        "articles": [
            {
                "restrict_xpaths": [
                    "//li[contains(@class,'article-list__item')]"
                ]
            }
        ],
        "navs": [
            {
                "restrict_xpaths": [
                    "//a[@rel='next']"
                ]
            }
        ]
    },
    "seeds": [
        {
        "url": "https://www.telegraph.co.uk/food-and-drink/",
        "meta": {
            "content_domain": "food",
            "content_subdomain": "food & drink",
            "playwright": True
        }
    },
        {
            "url": "https://www.telegraph.co.uk/recipes/",
            "meta": {
                "content_domain": "food",
                "content_subdomain": "recipes",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/fashion/",
            "meta": {
                "content_domain": "living",
                "content_subdomain": "fashion",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/beauty/",
            "meta": {
                "content_domain": "living",
                "content_subdomain": "beauty",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/gardening/",
            "meta": {
                "content_domain": "home",
                "content_subdomain": "gardening",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/gardening/",
            "meta": {
                "content_domain": "home",
                "content_subdomain": "gardening",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/health-fitness/diet/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "diet",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/health-fitness/fitness/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "fitness",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/health-fitness/conditions/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "conditions",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/health-fitness/wellbeing/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "well-being",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/health-fitness/parenting/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "parenting",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/health-fitness/guides/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "guides",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/money/investing/",
            "meta": {
                "content_domain": "money",
                "content_subdomain": "investing",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/money/property/",
            "meta": {
                "content_domain": "money",
                "content_subdomain": "property",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/money/guides/",
            "meta": {
                "content_domain": "money",
                "content_subdomain": "guides",
                "playwright": True
            }
        },
        {
            "url": "https://www.telegraph.co.uk/money/tax/",
            "meta": {
                "content_domain": "money",
                "content_subdomain": "tax",
                "playwright": True
            }
        }],
    "push_seed": True,
    "test_run": False
}

class TelegraphSpider(DailyLifeSpider):

    name = 'telegraph'
    allowed_domains = ['telegraph.co.uk']

    custom_settings = {
        'CONCURRENT_REQUESTS': 120,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 24,
        'DOWNLOAD_DELAY': 0
    }

    rules = [
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=[
                "//li[contains(@class,'article-list__item')]"
            ]
        ), callback='parse_article',
            process_request='_process_request'
        ),
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=[
                "//a[@rel='next']"
            ]
        ), follow=True, process_request='_process_request_nav')
    ]

    def _generate_rules(self):
        self.site_configs = {
            'telegraph.co.uk': self.config
        }

    seeds = CFG['seeds']
    config = DomainConfig(**CFG)

    def push_seed(self) -> int:
        server: Redis = self.server
        if not server:
            raise CloseSpider('unable to push seed, please check redis connection')
        for seed in self.seeds:
            if isinstance(seed,str):
                server.lpush(f"{self.name}:start_urls", seed)
            if url:=seed.get('url'):
                self.logger.info(f'pushed 1 seed with url {url}.')
                server.lpush(f"{self.name}:start_urls", json.dumps(seed))
        return len(self.seeds)

    def _apply_domain_config(self, request, config):
        super()._apply_domain_config(request,self.config)
        self.apply_playwright_meta(request,config)
        return request