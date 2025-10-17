
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

THEHEALTHY_COM_CONFIG = DomainConfig(
    domain="thehealthy.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//div[contains(@class,'category-card')]",
    navigation_xpaths=[
        "//a[contains(@class,'next page-numbers')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'health')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'beauty')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'exercise')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'food')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'nutrition')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'vitamins')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'weight-loss')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'aging')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'care')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'first-aid')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'home-remedies')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'dental')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'mental')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'healthcare')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'family')]",
        "//nav[@class='main-navigation-2021']//a[contains(@href, 'sex')]",
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
    notes="enthusiast brands group publishing"
)

# Auto-register
DomainConfigRegistry.register(THEHEALTHY_COM_CONFIG)
