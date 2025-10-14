
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

REFERENCE_COM_CONFIG = DomainConfig(
    domain="reference.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths=[
"//*[contains(@class,'article')]",
        "//*[contains(@id,'post')]",
    ],
    navigation_xpaths="//li[contains(@id,'menu-item')]",
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//span[@id='breadcrumblist']//a/span/text()",
    author_xpath="//span[@class='author']/text()",
    post_date_xpath="//span[@class='single-post-meta_updated']/text()",
    # Metadata
    lang="en",
    active=True,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(REFERENCE_COM_CONFIG)
