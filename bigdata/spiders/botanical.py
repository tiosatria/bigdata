from bigdata.spiders.universal import UniversalSpider


class BotanicalSpider(UniversalSpider):

    name = 'botanical'
    allowed_domains = ['botanical.com']
    start_urls = ['https://www.botanical.com/']

    use_proxy = True
