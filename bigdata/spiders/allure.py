from bigdata.spiders.common_pagination import CommonPaginationSpider


class AllureSpider(CommonPaginationSpider):
    name = 'allure'
    allowed_domains = ['allure.com']
    push_seed = True

    navigation_xpaths = [
        "//a[@class='BaseButton-lbLhfD ButtonWrapper-igqDZ ijhmCA fjIbcE button button--utility-pair']"
    ]

    content_xpaths = [
        "//div[@class='SummaryItemWrapper-ircKXK kqZFQE summary-item summary-item--has-no-final-border summary-item--no-icon summary-item--text-align-left summary-item--layout-placement-side-by-side-desktop-only summary-item--layout-position-image-left summary-item--layout-proportions-33-66 summary-item--side-by-side-align-center summary-item--side-by-side-image-right-mobile-false summary-item--standard SummaryItemWrapper-ircdWR llfpff summary-list__item']",
        "//div[@class='SummaryItemWrapper-ircKXK bsCvle summary-item summary-item--has-no-final-border summary-item--no-icon summary-item--text-align-center summary-item--layout-placement-text-below summary-item--layout-position-image-left summary-item--layout-proportions-50-50 summary-item--side-by-side-align-center summary-item--side-by-side-image-right-mobile-false summary-item--standard SummaryCollectionGridSummaryItem-HgAzv hbPaBa']"
    ]

    seeds = [
        {
            "url": "https://www.allure.com/wellness",
            "meta": {
                "content_subdomain": "wellness",
                "content_domain": "beauty"
            }
        },
        {
            "url": "https://www.allure.com/skin-care",
            "meta": {
                "content_subdomain": "skincare",
                "content_domain": "beauty"
            }
        },
        {
            "url": "https://www.allure.com/nails",
            "meta": {
                "content_subdomain": "nails",
                "content_domain": "beauty"
            }
        },
        {
            "url": "https://www.allure.com/hair-ideas",
            "meta": {
                "content_subdomain": "hair ideas",
                "content_domain": "beauty"
            }
        },
        {
            "url": "https://www.allure.com/makeup-looks",
            "meta": {
                "content_subdomain": "makeup",
                "content_domain": "beauty"
            }
        },
    ]
