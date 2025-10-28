from scrapy.exceptions import CloseSpider
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor

from bigdata.middlewares import ProxyMiddleware, FailedRequestExportMiddleware
from bigdata.spiders.base import RedisBaseCrawlSpider
from scrapy.spiders import Rule

class RdaenthusiastSpider(RedisBaseCrawlSpider):

    name = 'rdagroup'

    custom_settings = {
        'CONCURRENT_REQUESTS': 80,
        'AUTOTHROTTLE_TARGET_CONCURRENCY': 8,
        'DOWNLOAD_DELAY': 0.5,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 8,
        'COMPRESSION_ENABLED': False,
        'AUTOTHROTTLE_ENABLED': True,
        'LOG_LEVEL': 'DEBUG',
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': None,
            ProxyMiddleware: 350,
            'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 400,
            'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 500,
            FailedRequestExportMiddleware: 543
        },
        'REFERER_ENABLED': False
    }

    allowed_domains = ['tasteofhome.com', 'rd.com']

    push_seed = True

    bypass_cf = True

    rules = [
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=[
                "//div[contains(@class,'pure-g category-cards-container')]"
            ]), callback='parse_article', process_request='_apply_request_meta'),
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=[
                "//a[@class='next page-numbers']"
            ]), follow=True, process_request='_apply_request_meta')
    ]

    taste_of_home_seeds = [
        {
            "url": "https://www.tasteofhome.com/recipes",
            "meta": {
                "content_domain": "food",
                "content_subdomain": "recipes"
            }
        }
    ]

    rd_seeds = [
        {
            "url": "https://www.rd.com/food/",
            "meta": {
                "content_domain": "food",
            }
        },
        {
            "url": "https://www.rd.com/career-advice/",
            "meta": {
                "content_domain": "career",
                "content_subdomain": "advice"
            }
        },

        {
            "url": "https://www.rd.com/home/",
            "meta": {
                "content_domain": "home",
                "content_subdomain": "tips"
            }
        },

        {
            "url": "https://www.rd.com/money/",
            "meta": {
                "content_domain": "money",
            }
        },
        {
            "url": "https://www.rd.com/pets-animals/",
            "meta": {
                "content_domain": "pets",
            }
        },
        {
            "url": "https://www.rd.com/relationships",
            "meta": {
                "content_domain": "relationship",
                "content_subdomain": "advice & tips"
            }
        },
    ]

    seeds = []

    def __init__(self, site=None, *args, **kwargs):
        if not site:
            self.logger.error('site is required')
            raise CloseSpider('no_site')
        if site not in self.allowed_domains:
            self.logger.error(f'invalid site: {site}. available sites: {self.allowed_domains}')
            raise CloseSpider('invalid_site')
        if str.lower(site) == 'tasteofhome.com':
            self.allowed_domains = ['tasteofhome.com']
            self.seeds.extend(self.taste_of_home_seeds)
        if str.lower(site) == 'rd.com':
            self.allowed_domains = ['rd.com']
            self.seeds.extend(self.rd_seeds)
        super().__init__(*args, **kwargs)