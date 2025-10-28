from bigdata.spiders.common_pagination import CommonPaginationSpider


class ChildcarecenterSpider(CommonPaginationSpider):

    name = 'childcarecenter'
    allowed_domains = ['childcarecenter.us']

    push_seed = True

    seeds = [
        "https://childcarecenter.us/resources"
    ]

    content_xpaths = [
        "//div[@class='update']//h3/a"
    ]

    navigation_xpaths = [
        "//a[text()='Next »']"
    ]