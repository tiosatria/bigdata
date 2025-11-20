from typing import AsyncIterator, Any, Optional

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

    # AVAILABLE:

    # start_urls=[
    #     # "https://www.processon.com/template/search/flowchart_free", # 38
    #     # "https://www.processon.com/template/search/%E7%A8%8B%E5%BA%8F%E4%B8%BB%E7%A8%8B%E5%BA%8F%E6%B5%81%E7%A8%8B%E5%9B%BE_free" #851,
    #     # "https://www.processon.com/template/search/%E7%A8%8B%E5%BA%8F%E6%93%8D%E4%BD%9C%E6%B5%81%E7%A8%8B%E5%9B%BE_free" #893,
    #     "https://www.processon.com/template/search/%E7%A8%8B%E5%BA%8F%E6%A1%86%E5%9B%BE_free" #63,
    #     # "https://www.processon.com/template/search/%E7%AE%97%E6%B3%95%E6%B5%81%E7%A8%8B%E5%9B%BE_free" #836,
    # "https://www.processon.com/template/search/%E6%95%B0%E6%8D%AE%E5%BA%93%E6%B5%81%E7%A8%8B%E5%9B%BE_free" #1021
    # ]

    start_urls = [
        "https://www.processon.com/template/search/%E6%95%B0%E6%8D%AE%E5%BA%93%E6%B5%81%E7%A8%8B%E5%9B%BE_free",
    ]

    max_page_count = 1021

    custom_settings = {
        'FEEDS': {
            'output/flowcharts_links_data_1021.jsonl': {
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
        # for url in self.start_urls:
        #     yield scrapy.Request(url=url, callback=self.parse, meta={
        #         'current_page': 1,
        #         'use_proxy': True
        #     })

    def __init__(self, seed_urls:Optional[str]=None, *args, **kwargs):
        super(ProcessonLinkSpider, self).__init__(*args,**kwargs)
        urls = []
        if seed_urls:
            for url in seed_urls.split(','):
                urls.append(url.strip())
        if urls:
            self.start_urls=urls

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
            yield scrapy.Request(url=f'{self.start_urls[0]}_page{next_page}',
                                 meta={
                                     'current_page': next_page,
                                     'use_proxy': True
                                 })