from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor

from bigdata.middlewares import FailedRequestExportMiddleware, ProxyMiddleware
from bigdata.spiders.base import RedisBaseCrawlSpider
from scrapy.spiders import Rule

class DrugsSpider(RedisBaseCrawlSpider):

    name = 'drugs'

    allowed_domains = ['drugs.com']

    push_seed = True

    bypass_cf = True

    custom_settings = {
        'CONCURRENT_REQUESTS_PER_DOMAIN': 12,
        'DOWNLOAD_DELAY': 0,
        'LOG_LEVEL': 'DEBUG',
        'DOWNLOADER_MIDDLEWARES': {
            'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
            'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': None,
            ProxyMiddleware: 350,
            'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 400,
            'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 500,
            FailedRequestExportMiddleware: 543
        },
        'COMPRESSION_ENABLED': False,
    }

    rules = [
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=[
                "//div[@class='ddc-media-list ddc-mgt-2']",
                "//ul[@class='ddc-list-column-2']",
                "//div[@class='newsArchive']",
                "//div[@class='ddc-media-list']"
            ]
        ), callback='parse_article', process_request='_apply_request_meta'),
        Rule(link_extractor=LxmlLinkExtractor(
            allow_domains=allowed_domains,
            restrict_xpaths=[
                "//a[@aria-label='Next page']",
                "//nav[@aria-label='Drug list navigation by first letter']",
                "//div[@class='ddc-grid-col-6 col-list-az']",
                "//a[@aria-label='Next page']",
                "//dl[@class='ddc-mgt-2']"
            ]
        ), follow=True, process_request='_apply_request_meta')
    ]

    seeds = [
        {
            "url": "https://www.drugs.com/medical-answers/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "medical-answers"
            }
        },
        {
            "url": "https://www.drugs.com/alpha/a.html",
            "meta":{
                "content_domain": "health",
                "content_subdomain": "medications"
            }
        },
        {
            "url": "https://www.drugs.com/sfx/",
            "meta":{
                "content_domain": "medications",
                "content_subdomain": "side effects"
            }
        },
        {
            "url": "https://www.drugs.com/medical-news-archive/october-2025.html",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "prevention"
            }
        },
        {
            "url": "https://www.drugs.com/pregnancy-a1.html",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "pregnancy"
            }
        },
        {
            "url": "https://www.drugs.com/breastfeeding-a1.html",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "breastfeeding"
            }
        },
        {
            "url": "https://www.drugs.com/condition/a.html",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "conditions"
            }
        },
        {
            "url": "https://www.drugs.com/multa.html",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "conditions"
            }
        },
        {
            "url": "https://www.drugs.com/dosage-a0.html",
            "meta": {
                "content_domain": "medication",
                "content_subdomain": "dosage"
            }
        },
        {
            "url": "https://www.drugs.com/veta.html",
            "meta": {
                "content_domain": "medication",
                "content_subdomain": "vet"
            }
        },
        {
            "url": "https://www.drugs.com/otc-a1.html",
            "meta": {
                "content_domain": "medication",
                "content_subdomain": "over the counter"
            }
        },
        {
            "url": "https://www.drugs.com/otc-a1.html",
            "meta": {
                "content_domain": "medication",
                "content_subdomain": "over the counter"
            }
        },
        {
            "url": "https://www.drugs.com/international-a1.html",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "medication"
            }
        },
        {
            "url": "https://www.drugs.com/international-a1.html",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "medication"
            }
        },
        {
            "url": "https://www.drugs.com/answers/questions/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "medical faq"
            }
        },
        {
            "url": "https://www.drugs.com/lifestyle/",
            "meta": {
                "content_domain": "health",
                "content_subdomain": "lifestyle health faq"
            }
        },
    ]