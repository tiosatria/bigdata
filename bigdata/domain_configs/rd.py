
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

RD_COM_CONFIG = DomainConfig(
    domain="rd.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//div[contains(@class,'category-card')]",
    navigation_xpaths=[
        "//a[contains(@class,'next page-numbers')]",
        "//a[contains(@href, 'health')]",
        "//a[contains(@href, 'beauty')]",
        "//a[contains(@href, 'exercise')]",
        "//a[contains(@href, 'food')]",
        "//a[contains(@href, 'nutrition')]",
        "//a[contains(@href, 'vitamins')]",
        "//a[contains(@href, 'weight-loss')]",
        "//a[contains(@href, 'aging')]",
        "//a[contains(@href, 'care')]",
        "//a[contains(@href, 'first-aid')]",
        "//a[contains(@href, 'home-remedies')]",
        "//a[contains(@href, 'dental')]",
        "//a[contains(@href, 'mental')]",
        "//a[contains(@href, 'healthcare')]",
        "//a[contains(@href, 'sex')]",
        "//a[contains(@href, 'hair')]",
        "//a[contains(@href, 'house')]",
        "//a[contains(@href, 'decor')]",
        "//a[contains(@href, 'diy')]",
        "//a[contains(@href, 'gardening')]",
        "//a[contains(@href, 'organizing')]",
        "//a[contains(@href, 'pest-control')]",
        "//a[contains(@href, 'repair')]",
        "//a[contains(@href, 'home')]",
        "//a[contains(@href, 'money')]",
        "//a[contains(@href, 'pets')]",
        "//a[contains(@href, 'relationship')]",
        "//a[contains(@href, 'personal-technology')]",
        "//a[contains(@href, 'travel')]",
        "//a[contains(@href, 'career')]",
        "//a[contains(@href, 'advice')]",
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
    active=True,
    notes="enthusiast brands group publishing"
)

# Auto-register
DomainConfigRegistry.register(RD_COM_CONFIG)
