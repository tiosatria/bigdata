from redis import Redis
from scrapy import signals
from scrapy.exceptions import CloseSpider
from bigdata.spiders.dailylifespider import DailyLifeSpider

class TestSpider(DailyLifeSpider):

    name = 'test'
    max_test_limit = 10

    custom_settings = {
        'LOG_LEVEL': 'DEBUG',
        'COMPRESSION_ENABLED': True,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 1,
        'DOWNLOAD_DELAY': 3,
        'LOG_FILE': 'debug.log'
    }

    # def on_yielded_count_change(self):
    #     if self.yielded >= self.max_test_limit:
    #         raise CloseSpider('reached max test limit.')

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def push_seed(self) -> int:
        seeded = super().push_seed()
        if seeded < 1:
            raise CloseSpider("no seed in test run. ensure test_run flag is set to true")
        return seeded

    # reset queue after closed
    def spider_closed(self, spider: DailyLifeSpider):
        server :Redis = self.server
        if not server:
            self.logger.warning('unable to clear test session, please check redis connection')
        server.delete(f"{spider.name}:start_urls")
        server.delete(f"{spider.name}:requests")
        server.delete(f"{spider.name}:dupefilter")
        self.logger.info('cleared test session data')