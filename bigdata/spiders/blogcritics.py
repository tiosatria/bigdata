from bigdata.spiders.common_pagination import CommonPaginationSpider


class BlogCritics(CommonPaginationSpider):

    custom_settings = {
        'LOG_LEVEL': 'DEBUG'
    }

    name = 'blogcritics'
    allowed_domains = ['blogcritics.org']
    push_seed = True
    seeds = [
        {
            "url": "https://blogcritics.org/culture/food-and-drink/",
            "meta": {
                "content_subdomain": "food & drink",
                "content_domain": "food"
            }
        },
        {
            "url": "https://blogcritics.org/culture/health-and-fitness/",
            "meta": {
                "content_subdomain": "fitness",
                "content_domain": "health"
            }
        },
        {
            "url": "https://blogcritics.org/culture/personalfinance/",
            "meta": {
                "content_subdomain": "personal finance",
                "content_domain": "finance"
            }
        },
        {
            "url": "https://blogcritics.org/culture/tips-and-advice/",
            "meta": {
                "content_subdomain": "tips & advice",
                "content_domain": "life"
            }
        }
    ]

    content_xpaths = [
        "//div[@class='entry']/a"
    ]

    navigation_xpaths = [
        "//div[@class='pagination']"
    ]