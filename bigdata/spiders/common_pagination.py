from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor

from bigdata.spiders.base import RedisBaseCrawlSpider
from scrapy.spiders import Rule

class CommonPaginationSpider(RedisBaseCrawlSpider):

    allowed_domains = []

    navigation_xpaths :list[str]= []

    content_xpaths: list[str] = []

    seeds = []

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.rules = [
            Rule(LxmlLinkExtractor(
                allow_domains=self.allowed_domains,
                restrict_xpaths=self.content_xpaths),
                process_request=self._apply_request_meta,
                callback=self.parse_article),
            Rule(LxmlLinkExtractor(
                allow_domains=self.allowed_domains,
                restrict_xpaths=self.navigation_xpaths),
                follow=True,
                process_request=self._apply_request_meta)
        ]
        self._compile_rules()