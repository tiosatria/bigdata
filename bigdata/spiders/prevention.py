from scrapy_redis.spiders import RedisSpider

class PreventionSpider(RedisSpider):

    allowed_domains = ['preventionpoint.com']


