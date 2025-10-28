from bigdata.spiders.common_pagination import CommonPaginationSpider


class ThisOldHouseSpider(CommonPaginationSpider):

    name = 'thisoldhouse'
    allowed_domains = ['thisoldhouse.com']
    push_seed = True

    seeds = [
        "https://www.thisoldhouse.com/archives",
        
    ]

    content_xpaths = [
        "//div[@class='c-compact-river__entry']"
    ]

    navigation_xpaths = [
        "//a[@class='next p-button page-numbers']"
    ]