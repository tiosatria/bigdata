from bigdata.spiders.universal import UniversalSpider


class InternationalCuisineSpider(UniversalSpider):

    name = 'internationalcuisine'
    allowed_domains = ['internationalcuisine.com']

    seeds = []

    custom_settings = {
        'LOG_LEVEL': 'DEBUG',
        'COOKIES_ENABLED': False,
        'CONCURRENT_REQUESTS': 8,
    }

    use_proxy = False
    use_playwright = True