
from bigdata.spiders.article import ArticleSpider


class Article2(ArticleSpider):
    """
    Production-grade article spider with comprehensive error handling
    """

    name = 'article_2'
    redis_key = 'article:start_urls'

