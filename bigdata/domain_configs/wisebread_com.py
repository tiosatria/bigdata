from .domain_config import DomainConfig, RenderEngine
from . import DomainConfigRegistry

WISEBREAD_COM_CONFIG = DomainConfig(
    domain="wisebread.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//div[@class='teaser-container clearfix']",
    navigation_xpaths="//li[@class='pager-next']",
    max_pages=None,

    # Content extraction
    title_xpath="//h1[@class='page-title ']/text()",
    body_xpath="//div[@class='body']",
    tags_xpath="//div[@class='breadcrumb']/a/text()",
    author_xpath="//div[@class='credits']/a/text()",
    post_date_xpath="//span[@class='date']/text()",

    # Metadata
    lang="en",
    active=True,
    notes="testing wisebread"
)

# Auto-register
DomainConfigRegistry.register(WISEBREAD_COM_CONFIG)