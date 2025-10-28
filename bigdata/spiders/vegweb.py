from bigdata.spiders.universal import UniversalSpider


class VegWebSpider(UniversalSpider):

    name = 'vegweb'
    allowed_domains = ['vegweb.com']
    start_urls = ['https://www.vegweb.com/']

    use_proxy = True