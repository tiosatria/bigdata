import logging
from logging import LoggerAdapter
import trafilatura
from scrapy.responsetypes import Response
from bigdata.items import CrawlItem

class RequestAndResponseParser:

    logger = LoggerAdapter(logger=logging.getLogger(__name__), extra={})
    bypass_cf = False
    use_proxy = True
    use_playwright = False
    content_body_xpath = None

    def __init__(self,
                 logger:LoggerAdapter=None,
                 bypass_cf:bool=False,
                 use_proxy:bool=True,
                 use_playwright:bool=False,
                 content_body_xpath:str=None):
        if logger:
            self.logger = logger

        self.bypass_cf = bypass_cf
        self.use_proxy = use_proxy
        self.use_playwright = use_playwright
        self.content_body_xpath = content_body_xpath

    def _apply_playwright_meta(self, request):
        request.meta['playwright'] = True
        request.meta['playwright_page_goto_kwargs'] = {
            'wait_until': 'domcontentloaded',
        }

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
        self.logger.info(f"Yielded {metadata.get('title')} on : {response.url}")

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

    def _apply_request_meta(self, request, response):
        """Apply domain-specific configuration to request"""
        if self.bypass_cf:
            request.meta['bypass_cf'] = True
        if self.use_proxy:
            request.meta['use_proxy'] = True
        if self.use_playwright:
            self._apply_playwright_meta(request)
        return request