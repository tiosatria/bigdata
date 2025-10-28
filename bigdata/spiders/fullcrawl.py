import scrapy
import re

from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
from scrapy.spiders import Rule
from bigdata.spiders.base import RedisBaseCrawlSpider
from scrapy.responsetypes import Response


class FullCrawlSpider(RedisBaseCrawlSpider):

    allowed_domains = []

    deny_regexes : list[str] = []

    xpath_link_target : list[str]|str = None

    exclude_yield_url_regex : list[str] = []

    rules = [
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=xpath_link_target,
            deny=deny_regexes
        ), callback='_follow_and_parse', process_request='_apply_request_meta', follow=True)
    ]

    def _follow_and_parse(self, response:Response):

        pass