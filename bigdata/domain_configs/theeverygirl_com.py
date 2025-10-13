"""
Configuration for theeverygirl.com
Auto-generated configuration file

Notes: html
"""

from bigdata.domain_configs.domain_config import DomainConfig, ProxyConfig, RetryConfig, BotProtectionConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

THEEVERYGIRL_COM_CONFIG = DomainConfig(
    domain="theeverygirl.com",
    render_engine=RenderEngine.PLAYWRIGHT,

    # Navigation
    article_links_xpath=[
        "//div[@class='grid-item']"
    ],
    pagination_xpath=[
        "//div[@class='more']"
    ],
    max_pages=None,

    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//div[@class='post-intro__category meta']/a/text()",
    author_xpath="//div[@class='post-intro__writer']//a/text()",
    post_date_xpath="//time/[@class='post-intro__date meta']/text()",
    post_date_format=None,

    # Network settings
    download_delay=1.0,
    concurrent_requests=2,
    retry_config=RetryConfig(
        max_retries=3,
        retry_http_codes=[403, 429, 500, 502, 503, 504],
        backoff_factor=2.0,
        priority_boost=10
    ),
    bot_protection=BotProtectionConfig(
        enabled=True,
        use_stealth_mode=True
    ),

    # Metadata
    lang="en",
    active=False,
    notes="html"
)

# Auto-register
DomainConfigRegistry.register(THEEVERYGIRL_COM_CONFIG)
