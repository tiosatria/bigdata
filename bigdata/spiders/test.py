from scrapy import signals
from redis import Redis
from scrapy.exceptions import CloseSpider

from bigdata.spiders.dailylifespider import DailyLifeSpider

class TestSpider(DailyLifeSpider):

    name = 'test'
    max_test_limit = 10

    custom_settings = {
        'LOG_LEVEL': 'DEBUG',
        'COMPRESSION_ENABLED': True,
        'CONCURRENT_REQUESTS_PER_DOMAIN': 2
    }

    def on_yielded_count_change(self):
        if self.yielded >= self.max_test_limit:
            raise CloseSpider('reached max test limit.')

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        spider = super().from_crawler(crawler, *args, **kwargs)
        crawler.signals.connect(spider.spider_closed, signal=signals.spider_closed)
        return spider

    def spider_closed(self, spider: DailyLifeSpider):
        server :Redis = self.server
        if not server:
            self.logger.warning('unable to clear test session, please check redis connection')
        server.delete(f"{spider.name}:start_urls")
        server.delete(f"{spider.name}:requests")
        server.delete(f"{spider.name}:dupefilter")
        self.logger.info('cleared test session data')

    def push_test_seed(self):
        server: Redis = self.server
        seeded = 0
        if not server:
            raise CloseSpider('unable to push test seed, please check redis connection')
        for domain, config in self.site_configs.items():
            self.logger.debug(f'Attempting to push seed for domain: {domain}')
            if not config.test_run:
                continue
            for seed in config.seeds:
                if url:=seed.get('url'):
                    self.logger.info(f'pushed 1 seed with url {url}. for domain: {domain}')
                    server.rpush(f"{self.name}:start_urls", url)
                    seeded+=1

        if seeded < 1:
            raise CloseSpider("no seed in test run. ensure test_run flag is set to true")

    def start_requests(self):
        self.push_test_seed()
        super().start_requests()