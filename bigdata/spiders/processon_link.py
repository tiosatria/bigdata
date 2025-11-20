from typing import AsyncIterator, Any

import scrapy
from scrapy.http import Response


# def get_current_page(url: str) -> int:
#     if not url:
#         return 0
#     parts = url.split('_free_')
#     if len(parts) < 2:
#         return 1
#     else:
#         try:
#             pageStr = parts[1]
#             page = pageStr.replace('page', '')
#             return int(page)
#         except:
#             return 1

class ProcessonLinkSpider(scrapy.spiders.Spider):

    name = "processon_link"
    allowed_domains = ["processon.com"]

    start_urls = ['https://www.processon.com/template/search/%E7%A8%8B%E5%BA%8F%E6%B5%81%E7%A8%8B%E5%9B%BE_free']

    max_page_count = 851

    custom_settings = {
        'FEEDS': {
            'output/flowcharts_links_data.jsonl': {
                'format': 'jsonlines',
                'encoding': 'utf8',
                'overwrite': False,
            },
        },
        'ITEM_PIPELINES': {},
        'RETRY_TIMES': 10,
        'CONCURRENT_REQUESTS': 100,  # Can be higher since no rendering
        'CONCURRENT_REQUESTS_PER_DOMAIN': 50,
    }

    async def start(self) :
        yield scrapy.Request(url=self.start_urls[0], callback=self.parse, meta={
            'current_page': 1,
            'use_proxy': True
        })

    def parse(self, response: Response, **kwargs: Any) -> Any:
        items = response.xpath("//a[@class='item-title-a']")
        current_page = response.meta.get('current_page', 1)

        for item in items:
            yield {
                'ref_url': response.url,
                'from_page': current_page,
                'url': item.xpath("./@href").get(),
                'title': item.xpath("./text()").get()
            }
        self.logger.info(f'Yielded chart links from page : {current_page}. Url: {response.url}')
        if current_page < self.max_page_count:
            self.logger.info(f'Navigating to next page: {current_page}')
            next_page = current_page + 1
            yield scrapy.Request(url=f'https://www.processon.com/template/search/%E7%A8%8B%E5%BA%8F%E6%B5%81%E7%A8%8B%E5%9B%BE_free_page{next_page}',
                                 meta={
                                     'current_page': next_page,
                                     'use_proxy': True
                                 })