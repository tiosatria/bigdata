# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

from scrapy import Field, Item
from typing_extensions import deprecated


@deprecated("Use CrawlItem instead", category=FutureWarning)
class ArticleItem(Item):
    url = Field()
    source_domain = Field()
    title = Field()
    tags = Field()
    author = Field()
    post_date = Field()
    body = Field()
    body_type = Field()
    body_content = Field()
    lang = Field()
    timestamp = Field()

class CrawlItem(Item):
    meta = Field()
    body = Field()

class DailyLifeResult(Item):
    id = Field()
    text = Field()
    meta = Field()