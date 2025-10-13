
from bigdata.domain_configs.domain_config import DomainConfig, ProxyConfig, RetryConfig, BotProtectionConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

COOKS_COM_CONFIG = DomainConfig(
    domain="cooks.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_links_xpath="//div[@class='regular']",
    pagination_xpath="//div[@style='text-align: center;']",
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//tbody",
    tags_xpath="//a[@class='lnk']/text()",
    author_xpath=None,
    post_date_xpath=None,
    post_date_format=None,

    # Network settings
    download_delay=0.6,
    concurrent_requests=4,
    retry_config=RetryConfig(
        max_retries=3,
        retry_http_codes=[403, 429, 500, 502, 503, 504],
        backoff_factor=2.0,
        priority_boost=10
    ),
    bot_protection=BotProtectionConfig(
        enabled=False,
        use_stealth_mode=True
    ),

    # Metadata
    lang="en",
    active=True,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(COOKS_COM_CONFIG)
