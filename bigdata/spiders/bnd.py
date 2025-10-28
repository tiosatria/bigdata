from bigdata.spiders.common_pagination import CommonPaginationSpider


class BndSpider(CommonPaginationSpider):

    name = 'bnd'
    allowed_domains = ['bnd.com']
    push_seed = True

    seeds = [
        {
            "url": "https://www.bnd.com/living/food-drink/",
            "meta": {
                "content_domain": "culinary",
                "content_subdomain": "food & drink"
            }
        }
    ]