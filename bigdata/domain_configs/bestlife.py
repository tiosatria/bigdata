
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

BESTLIFEONLINE_COM_CONFIG = DomainConfig(
    domain="bestlifeonline.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths=[
        "//div[@class='main-posts-list']"],

    navigation_xpaths=[
        "//a[@class='gnp-page-nav__button']",
    ],

    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[contains(@class,'content')]",
    tags_xpath="//a[@rel='tag']/text()",
    author_xpath="//*[contains(@id,'author') or contains(@class,'author')]",
    post_date_xpath="//div[@class='date']/text()",
    # Metadata
    lang="en",
    active=True,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(BESTLIFEONLINE_COM_CONFIG)