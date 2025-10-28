from typing import AsyncIterator, Any

from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor

from bigdata.middlewares import FailedRequestExportMiddleware, ProxyMiddleware
from bigdata.spiders.base import RedisBaseCrawlSpider
from scrapy.spiders import Rule
import scrapy

from bigdata.spiders.base_parser import RequestAndResponseParser


class TheHealthySpider(scrapy.Spider):

    name = 'thehealth'

    custom_settings = {
        'CONCURRENT_REQUESTS': 12,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 12,
        'DOWNLOAD_DELAY': 0.5,
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
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.parser = RequestAndResponseParser(logger=self.logger, bypass_cf=True)

    async def start(self) -> AsyncIterator[Any]:

        yield scrapy.Request(
            url="https://www.thehealthy.com/health-a-z/",
            callback=self.parse_content,
            meta={
                "content_domain": "health",
                "content_subdomain": "health-a-z",
                "bypass_cf" : True,
                "depth": 0
            }
        )

    def parse_content(self, response):
        self.logger.info(f"Parsing {response.url}")
        depth = response.meta["depth"]
        if depth > 1:
            yield from self.parser.parse_article(response)
            return
        link = LxmlLinkExtractor(restrict_xpaths="//div[@class='site-inner']/ul",
                                 allow_domains=["thehealthy.com"])
        for link in link.extract_links(response):
            yield scrapy.Request(
                url=link.url,
                callback=self.parse_content,
                meta={
                    "content_domain": "health",
                    "content_subdomain": "health-a-z",
                    "depth": depth + 1,
                    "bypass_cf" : True,
                }
            )




