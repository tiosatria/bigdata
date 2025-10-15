
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

GARDENGUIDES_COM_CONFIG = DomainConfig(
    domain="gardenguides.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths="//article",
    navigation_xpaths=["//a[@id='next-page']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//ul[@class='breadcrumbs']/li/a/text()",
    author_xpath="//a[@class='byline-author']/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(GARDENGUIDES_COM_CONFIG)
