from redis import Redis
from scrapy import signals
from scrapy.exceptions import CloseSpider
from scrapy_redis.spiders import RedisCrawlSpider

from bigdata.spiders.dailylifespider import DailyLifeSpider

class TestSpider(DailyLifeSpider):

    name = 'test'
    max_test_limit = 10

    custom_settings = {
        'LOG_LEVEL': 'DEBUG',
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'DOWNLOAD_DELAY': 1,
        # 'LOG_FILE': 'debug.log'
    }

    def spider_idle(self):
        super().spider_idle()
        if self.yielded >= self.max_test_limit:
            raise CloseSpider('reached max test limit.')

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    # reset queue after closed
    def spider_closed(self, spider: DailyLifeSpider):
        server :Redis = self.server
        if not server:
            self.logger.warning('unable to clear test session, please check redis connection')
        server.delete(f"{spider.name}:start_urls")
        server.delete(f"{spider.name}:requests")
        server.delete(f"{spider.name}:dupefilter")
        self.logger.info('cleared test session data')