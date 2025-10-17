
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

BIRDSANDBLOOMS_COM_CONFIG = DomainConfig(
    domain="birdsandblooms.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//div[contains(@class,'category-card')]",
    navigation_xpaths=[
        "//a[contains(@class,'next page-numbers')]",
        "//nav[@class='main-navigation-2021']//a[contains(@class,'next')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'birding')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'gardening')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'backyard')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'travel')]",
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//section[contains(@class,'content-wrapper')] | //div[@class='post-content']",
    tags_xpath="//nav[@class='breadcrumbs']/a/text()",
    author_xpath="//a[@data-module='author-header']/text()",
    post_date_xpath="//p[@class='post-updated-date']/text()",
    # Metadata
    lang="en",
    active=False,
    notes="enthusiast brands group publishing",
    cloudflare_proxy_bypass=True
)

# Auto-register
DomainConfigRegistry.register(BIRDSANDBLOOMS_COM_CONFIG)
