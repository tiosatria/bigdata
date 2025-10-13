
from bigdata.domain_configs.domain_config import DomainConfig, ProxyConfig, RetryConfig, BotProtectionConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

COOKS_COM_CONFIG = DomainConfig(
    domain="cooks.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//div[@class='regular']",
    navigation_xpaths="//div[@style='text-align: center;']",
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//tbody",
    tags_xpath="//a[@class='lnk']/text()",
    author_xpath=None,
    post_date_xpath=None,
    # Metadata
    lang="en",
    active=True,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(COOKS_COM_CONFIG)
