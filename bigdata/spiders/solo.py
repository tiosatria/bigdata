
from bigdata.spiders.article import ArticleSpider


class SoloSpider(ArticleSpider):
    """
    Solo
    """

    name = 'solo'
    redis_key = 'solo:start_urls'

    custom_settings = {
        'LOG_LEVEL': 'DEBUG',
        'CONCURRENT_REQUESTS_PER_DOMAIN': 20,
        'COOKIES_ENABLED': True,
        'REFERER_ENABLED': True
    }

