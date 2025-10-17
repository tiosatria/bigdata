from scrapy import signals

from bigdata.spiders.article import ArticleSpider
from redis import Redis

class TestSpider(ArticleSpider):
    """
    Production-grade article spider with comprehensive error handling
    """

    name = 'test'
    redis_key = 'test:start_urls'

    custom_settings = {
        'LOG_LEVEL': 'DEBUG',
        'COMPRESSION_ENABLED': True,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'CONCURRENT_REQUESTS': 1,
        'DOWNLOAD_DELAY': 2,
    }

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def spider_closed(self, spider):
        server : Redis = self.server
        if not server:
            self.logger.warning('unable to clear test session, please check redis connection')
        server.delete(f"{spider.name}:start_urls")
        server.delete(f"{spider.name}:requests")
        server.delete(f"{spider.name}:dupefilter")
        self.logger.info('cleared test session data')
