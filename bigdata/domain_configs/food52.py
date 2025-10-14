
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

FOOD52_COM_CONFIG = DomainConfig(
    domain="food52.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths=[
        "//a[contains(@id,'mntl-card-list-items')]"],

    navigation_xpaths=[
        "//a[@class='gnp-page-nav__button']",
        "//ul[@class='loc mntl-link-list']"
    ],

    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//ul[contains(@id,'breadcrumbs')]/a/span/text()",
    author_xpath="//a[@class='mntl-attribution__item-name']/text()",
    post_date_xpath="//div[@class='mntl-attribution__item-date']/text()",
    # Metadata
    lang="en",
    active=True,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(FOOD52_COM_CONFIG)