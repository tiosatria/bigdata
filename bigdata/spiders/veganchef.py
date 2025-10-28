from bigdata.spiders.universal import UniversalSpider


class VeganchefSpider(UniversalSpider):

    name = 'veganchef'
    allowed_domains = ['veganchef.com']
    start_urls = ['https://veganchef.com/']

    use_proxy = True