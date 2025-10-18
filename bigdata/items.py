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
    body = scrapy.Field()  # Cleaned raw HTML (OBVIOUS_EXCLUDES applied)
    body_type = scrapy.Field()
    body_content = scrapy.Field()  # NEW: Trafilatura cleaned text with formatting (preserves images/tables)
    extraction_method = scrapy.Field()  # NEW: "trafilatura", "xpath", or "hybrid"
    lang = scrapy.Field()
    timestamp = scrapy.Field()