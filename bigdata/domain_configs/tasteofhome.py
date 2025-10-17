
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

TASTEOFHOME_COM_CONFIG = DomainConfig(
    domain="tasteofhome.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//div[contains(@class,'category-card')]",
    navigation_xpaths=[
        "//a[contains(@class,'next page-numbers')]",
        "//li[contains(@class,'menu-item')]//a[contains(@class,'next')]",
        "//li[contains(@class,'menu-item')]//a[contains(@href, 'recipes')]",
        "//li[contains(@class,'menu-item')]//a[contains(@href, 'tools')]",
        "//li[contains(@class,'menu-item')]//a[contains(@href, 'gear')]",
        "//li[contains(@class,'menu-item')]//a[contains(@href, 'health')]",
        "//li[contains(@class,'menu-item')]//a[contains(@href, 'holidays')]",
        "//li[contains(@class,'menu-item')]//a[contains(@href, 'home-living')]",
        "//li[contains(@class,'menu-item')]//a[contains(@href, 'skills')]",
        "//li[contains(@class,'menu-item')]//a[contains(@href, 'test-kitchen')]",
        "//li[contains(@class,'menu-item')]//a[contains(@href, 'collection')]",
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
DomainConfigRegistry.register(TASTEOFHOME_COM_CONFIG)
