# Define here the models for your scraped items
#
# See documentation in:
# https://docs.scrapy.org/en/latest/topics/items.html

import scrapy

class ArticleItem(scrapy.Item):
    url = scrapy.Field()
    source_domain = scrapy.Field()
    title = scrapy.Field()
    tags = scrapy.Field()
    author = scrapy.Field()
    post_date = scrapy.Field()
    body = scrapy.Field()
    body_type = scrapy.Field()
    lang = scrapy.Field()
    timestamp = scrapy.Field()