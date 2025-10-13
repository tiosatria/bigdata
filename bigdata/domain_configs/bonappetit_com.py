"""
Configuration for bonappetit.com
Auto-generated configuration file

Notes: use custom parser
"""

from bigdata.domain_configs.domain_config import DomainConfig, ProxyConfig, RetryConfig, BotProtectionConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

BONAPPETIT_COM_CONFIG = DomainConfig(
    domain="bonappetit.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_links_xpath="//div[contains(@class,'StackedRatingsCardWrapper')]",
    pagination_xpath=[
        "//div[@class='PaginationButtonWrapper-dDcSxp iwYgIg']"
    ],
    max_pages=None,
    custom_parser="parse_bonappetit",
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//script[@type='application/ld+json']/text()",
    tags_xpath=None,
    author_xpath=None,
    post_date_xpath=None,
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
        enabled=False,
        use_stealth_mode=True
    ),

    # Metadata
    lang="en",
    active=True,
    notes="use custom parser"
)

# Auto-register
DomainConfigRegistry.register(BONAPPETIT_COM_CONFIG)
