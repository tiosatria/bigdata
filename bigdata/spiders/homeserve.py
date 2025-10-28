from typing import Any

import scrapy
from scrapy.http import Response, TextResponse
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
import trafilatura
from bigdata.items import CrawlItem


# do it later

class HomeServeSpider(scrapy.Spider):
    name = "homeserve"
    allowed_domains = ["homeserve.com"]

    custom_settings = {
        'COMPRESSION_ENABLED': False,
    }


    async def start(self):

        req = scrapy.Request.from_curl("""
        curl 'https://graphql.contentful.com/content/v1/spaces/zg6rxnmxxp2o/environments/master' \
  -H 'accept: */*' \
  -H 'accept-language: en-US,en;q=0.9' \
  -H 'authorization: Bearer qYDi0Pb0Rcnr2RVaTesDZNFTd5RLKYvEjvMkbMR3ZpU' \
  -H 'content-type: application/json' \
  -H 'origin: https://www.homeserve.com' \
  -H 'priority: u=1, i' \
  -H 'referer: https://www.homeserve.com/' \
  -H 'sec-ch-ua: "Google Chrome";v="141", "Not?A_Brand";v="8", "Chromium";v="141"' \
  -H 'sec-ch-ua-mobile: ?0' \
  -H 'sec-ch-ua-platform: "Windows"' \
  -H 'sec-fetch-dest: empty' \
  -H 'sec-fetch-mode: cors' \
  -H 'sec-fetch-site: cross-site' \
  -H 'user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36' \
  --data-raw '{"query":"query {\n      pageLayoutArticleCollection(order: publishDate_DESC, skip: 16, limit: 8, preview: false) {\n        total\n        items {\n          \n  category\n  pageName\n  articleHeadLine\n  publishDate\n  pageComponentsCollection {\n    items {\n      ... on FragmentArticleContent {\n        __typename\n        banner\n        authorName\n        metaDescription\n        blogAbstract {\n          json\n        }\n        podioData {\n          json\n        }\n      }\n    }\n  }\n\n        }\n      }\n    }"}'
        """)
        req.callback = self.parse
        req.meta['bypass_cf'] = True
        req.meta['is_content'] = False
        yield req



    def parse(self, response: Response, **kwargs: Any) -> Any:



        links = LxmlLinkExtractor(restrict_xpaths="///div[contains(@class,'index_article')]",
                                  allow_domains=self.allowed_domains,
                                  allow='/en-us/blog/?').extract_links(TextResponse(url=response.url, body=response.text, encoding='utf-8'))
        for link in links:
            yield scrapy.Request(url=link.url,
                                 callback=self.parse_article,
                                 meta= {
                'bypass_cf': True,
                'is_content': True,
                'referer': response.url,
            })

        current_page = response.meta.get('current_page',1)
        has_next = current_page < self.max_page
        if has_next:
            n = current_page + 1
            self.logger.info(f'Moving to next page: {n}')
            next_url = f'https://www.homeserve.com/en-us/blog?page={n}'
            yield scrapy.Request(url=next_url, callback=self.parse, meta={
                'current_page': n,
                'bypass_cf': True,
                'is_content': False
            })
        else:
            self.logger.info('Reached at the end of the page. ✅')

    def get_and_set_metadata(self, response: Response):
        metadata = (trafilatura
                    .extract_metadata(response.text,
                                      default_url=response.url)
                    .as_dict())
        metadata['body_type'] = 'html'
        if cs := response.meta.get('content_subdomain'):
            metadata['content_subdomain'] = cs
        if cd := response.meta.get('content_domain'):
            metadata['content_domain'] = cd
        return metadata

    def parse_article(self, response: Response, **kwargs: Any) -> Any:

        metadata = self.get_and_set_metadata(response)
        body = response.text

        # Additional validation: check if trafilatura found a title
        if not metadata.get('title'):
            self.logger.info(f'No title found, skipping: {response.url} ❌')
            return

        metadata['referer'] = response.meta.get('referer')
        metadata['is_content'] = 'true'

        self.logger.info(f'Yielding {metadata.get("title")} on: {response.url} ✅')

        yield CrawlItem(
            meta=metadata,
            body=body
        )

        # should we follow the related link? idk.

