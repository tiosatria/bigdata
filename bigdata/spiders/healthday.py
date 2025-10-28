from typing import Iterable, Any, AsyncIterator

import scrapy

class HealthdaySpider(scrapy.Spider):

    name = "healthday"

    # est
    max_item = 19200
    max_item_per_page = 20

    offset = 0
    limit = max_item_per_page

    seeds = [
        f"https://www.healthday.com/api/v1/collections/health-news?item-type=story&offset={offset}&limit={limit}",
        f"https://www.healthday.com/api/v1/collections/healthday-tv?item-type=story&offset=5&limit=8",
        f"https://www.healthday.com/api/v1/collections/a-to-z-health?item-type=story&offset=13&limit=8",
        f"https://www.healthday.com/api/v1/collections/healthday-now?item-type=story&offset=8&limit=8"
    ]



    async def start(self) -> AsyncIterator[Any]:
        pass











