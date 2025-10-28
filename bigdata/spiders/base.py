from scrapy.exceptions import CloseSpider
from scrapy.http import TextResponse
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
from scrapy_redis.spiders import RedisCrawlSpider
from redis import Redis
from scrapy.responsetypes import Response
import trafilatura
from bigdata.items import CrawlItem
import json

class RedisBaseCrawlSpider(RedisCrawlSpider):

    seeds : list[str | dict] = []

    content_body_xpath : str = None

    bypass_cf : bool = False
    use_proxy : bool = True
    use_playwright : bool = False
    push_seed :bool = False

    def _push_seed(self) -> int:
        self.logger.info(f'seed available: {len(self.seeds)} seeds')
        self.logger.info(f'pushing: {self.push_seed}')
        if not self.push_seed or not self.seeds:
            return 0
        server: Redis = self.server
        seeded = 0
        if not server:
            raise CloseSpider('unable to push seed, please check redis connection')
        for seed in self.seeds:
            if isinstance(seed,str):
                server.lpush(f"{self.name}:start_urls", seed)
                continue
            if not isinstance(seed,dict):
                self.logger.warning(f'invalid seed type: {type(seed).__name__}. seed type can only be str or dict.')
                continue
            if url:=seed.get('url'):
                self.logger.info(f'pushed 1 seed with url {url}.')
                if self.bypass_cf:
                    seed['meta']['bypass_cf'] = True
                if self.use_proxy:
                    seed['meta']['use_proxy'] = True
                if self.use_playwright:
                    seed['meta']['playwright'] = True
                    seed['meta']['playwright_page_goto_kwargs'] = {
                        'wait_until': 'domcontentloaded',
                    }
                server.lpush(f"{self.name}:start_urls", json.dumps(seed))
                seeded+=1
        return seeded

    def start_requests(self):
        self.logger.info(f'Starting spider {self.name}')
        self._push_seed()
        return super().start_requests()

    def parse_article(self, response: Response):
        bx = self.content_body_xpath
        metadata = self.get_and_set_metadata(response)
        body = response.xpath(bx).get() if bx else response.text
        if not body:
            self.logger.debug('no body xpath container were found, falling back to raw body')
            body = response.text
        yield CrawlItem(
            meta=metadata,
            body=body
        )
        self.logger.info(f'Yielded {metadata.get('title')} on : {response.url}')

    def _apply_playwright_meta(self, request):
        request.meta['playwright'] = True
        request.meta['playwright_page_goto_kwargs'] = {
            'wait_until': 'domcontentloaded',
        }

    def _apply_request_meta(self, request, response):
        """Apply domain-specific configuration to request"""
        if self.bypass_cf:
            request.meta['bypass_cf'] = True
        if self.use_proxy:
            request.meta['use_proxy'] = True
        if self.use_playwright:
            self._apply_playwright_meta(request)
        return request

    def get_and_set_metadata(self, response:Response):
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