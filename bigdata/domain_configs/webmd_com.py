
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

WEBMD_COM_CONFIG = DomainConfig(
    domain="webmd.com",
    site_subdomains=["blogs.webmd.com"],
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//ul[@class='link-list']",
        "//ul[@class='list']",
        "//div[@class='drugs-search-list-conditions']",
        "//ul[@class='browse-letters squares']",
        "//div[@data-metrics-module='vs-az']",
        "//section[contains(@class,'toc-section')]",
        "//section[contains(@class,'toc-guide-chapter')]",
        "//ol[contains(@class,'chapter')]",
        "//li[contains(@class,'slider-item')]",
        "//ol[@class='section']",
        "//div[@class='recommended-module-link']",
        "//div[@class='latest-post-data']",
        "//div[@class='prx-rss-dlist']",
        "//div[@class='card']"
    ],
    navigation_xpaths=[
        #letter nav
        "//nav[@class='letter-nav']",
        "//div[@class='webmd-pagination-anchor-based']",
        "//div[@data-metrics-module='drugs-az']",
        "//a[contains(@href,'default.htm') and not(contains(@href,'tool'))]",
        "//a[@class='view-all-link']",
        "//a[@class='navlink nextlink']",
        "//div[@class='prx-rss-alphabet']"
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text() | //*[contains(@class,'title')]/text() | //*[contains(@id,'title')]",
    body_xpath="//article | //div[@class='faq-section']",
    tags_xpath="//ul[@class='breadcrumbs']/li/a/text()",
    author_xpath="//span[@class='person']/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="",
    domain_type="health & wellness",
    subdomain_type="wellness/disease/prevention",
    seeds=[
        Seed(url="https://www.webmd.com/a-to-z-guides/health-topics"),
        Seed(url="https://www.webmd.com/a-to-z-guides/medical-reference/default.htm"),
        Seed(url="https://www.webmd.com/a-to-z-guides/news-features"),
        Seed(url="https://www.webmd.com/a-to-z-guides/news/default.htm"),
        Seed(url="https://www.webmd.com/drugs/2/alpha/a"),
        Seed(url="https://www.webmd.com/interaction-checker/default.htm"),
        Seed(url="https://www.webmd.com/sitemap")
    ])

DomainConfigRegistry.register(WEBMD_COM_CONFIG)

