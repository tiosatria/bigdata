
from bigdata.spiders.common_pagination import CommonPaginationSpider
from scrapy.spiders import Rule
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor

class FoodAndDrinkSpider(CommonPaginationSpider):

    name = 'fooddrinktalk'
    allowed_domains = ['fooddrinktalk.com']
    push_seed = True

    use_proxy = False

    custom_settings = {
        'LOG_LEVEL': 'DEBUG'
    }

    content_body_xpath = "//div[@class='inside-article']"
    content_xpaths = "//h2[@class='entry-title']"
    navigation_xpaths = "//a[@class='next page-numbers']"

    rules = [
        Rule(link_extractor=LxmlLinkExtractor(allow_domains=allowed_domains,
                                              restrict_xpaths=content_xpaths),
             process_request='_apply_request_meta',
             callback='parse_article'),
        Rule(link_extractor=LxmlLinkExtractor(allow_domains=allowed_domains,
                                              restrict_xpaths=navigation_xpaths),
             follow=True,
             process_request='_apply_request_meta')
    ]

    seeds = [
        "https://fooddrinktalk.com/"
    ]
