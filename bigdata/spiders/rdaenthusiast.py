from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor

from bigdata.middlewares import ProxyMiddleware, FailedRequestExportMiddleware
from bigdata.spiders.base import RedisBaseCrawlSpider
from scrapy.spiders import Rule

class RdaenthusiastSpider(RedisBaseCrawlSpider):

    name = 'rdagroup'

    custom_settings = {
        'CONCURRENT_REQUESTS': 128,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 24,
        'COMPRESSION_ENABLED': False,
        'DOWNLOAD_DELAY': 0,
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': None,
            ProxyMiddleware: 350,
            'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 400,
            'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 500,
            FailedRequestExportMiddleware: 543
        },
    }

    allowed_domains = ['tasteofhome.com']

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

    seeds = [
        {
            "url": "https://www.tasteofhome.com/recipes/",
            "meta": {
                "content_domain": "food",
                "content_subdomain": "recipes"
            }
        }, {
            "url": "https://www.tasteofhome.com/home-living/",
            "meta": {
                "content_domain": "home",
                "content_subdomain": "living"
            }
        }, {
            "url": "https://www.tasteofhome.com/health-wellness/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "wellness"
            }
        }
    ]





