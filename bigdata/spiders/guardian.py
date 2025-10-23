import json

from redis import Redis
from scrapy.exceptions import CloseSpider
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor

from bigdata.spiders.dailylifespider import DailyLifeSpider, DomainConfig
from scrapy.spiders import Rule

CFG : dict = {
      "domain": "theguardian.com",
      "use_proxy": True,
      "use_playwright": True,
      "link_extractors": {
        "articles": [
          {
            "restrict_xpaths": [
              "//div[contains(@id,'container-')]//li"
            ]
          }
        ],
        "navs": [
          {
            "restrict_xpaths": [
              "//a[@class='dcr-jh1m5g']"
            ]
          }
        ]
      },
      "active": True,
      "seeds": [
        {
          "url": "https://www.theguardian.com/food?page=579",
          "meta": {
            "content_domain": "food",
            "content_subdomain": "cooks",
            "playwright": True
          }
        }
      ],
      "push_seed": True,
      "test_run": False
    }

# this thing is running abnormally, feel free to check telegraph.py for normal operation
class GuardianSpider(DailyLifeSpider):

    name = 'guardian'

    allowed_domains = ['theguardian.com']

    custom_settings = {
        'CONCURRENT_REQUESTS': 80,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,
        'AUTOTHROTTLE_ENABLED' : True,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 8,
        'DOWNLOAD_DELAY': 0.5,
    }

    rules = [
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=[
                "//div[contains(@id,'container-')]//li"
            ],
        ), callback='parse_article', process_request='_process_request'),
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=["//a[@class='dcr-jh1m5g']"]
        ), follow=True, process_request='_process_request_nav')
    ]

    seeds =[
        {
            "url": "https://www.theguardian.com/food?page=579",
            "meta": {
                "content_domain": "food",
                "content_subdomain": "cooks",
                "playwright": True
            }
        },{
            "url": "https://www.theguardian.com/tone/recipes?page=9",
            "meta": {
                "content_domain": "food",
                "content_subdomain": "recipes",
                "playwright": True
            }
        },{
          "url": "https://www.theguardian.com/lifeandstyle/health-and-wellbeing?page=26",
          "meta": {
            "content_domain": "health",
            "content_subdomain": "wellbeing",
            "playwright": True
          }
        },
        {
          "url": "https://www.theguardian.com/lifeandstyle/homes?page=9",
          "meta": {
            "content_domain": "home",
            "content_subdomain": "home & garden",
            "playwright": True
          }
        },   {
          "url": "https://www.theguardian.com/money?page=27",
          "meta": {
            "content_domain": "living",
            "content_subdomain": "money",
            "playwright": True
          }
        }
    ]

    config = DomainConfig(domain=allowed_domains[0])

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



