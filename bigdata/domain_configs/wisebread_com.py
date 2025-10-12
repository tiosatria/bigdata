"""
Configuration for wisebread.com
Auto-generated configuration file

Notes: testing wisebread
"""

from .domain_config import DomainConfig, ProxyConfig, RetryConfig, BotProtectionConfig, RenderEngine
from . import DomainConfigRegistry

WISEBREAD_COM_CONFIG = DomainConfig(
    domain="wisebread.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_links_xpath="//div[@class='teaser-container clearfix']",
    pagination_xpath="//li[@class='pager-next']",
    max_pages=None,

    # Content extraction
    title_xpath="//h1[@class='page-title ']/text()",
    body_xpath="//div[@class='body']",
    tags_xpath="//a[@sl-processed='1']/text()",
    author_xpath="//div[@class='credits']/a/text()",
    post_date_xpath="//span[@class='date']/text()",
    post_date_format=None,

    # Network settings
    download_delay=0.8,
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
    notes="testing wisebread"
)

# Auto-register
DomainConfigRegistry.register(WISEBREAD_COM_CONFIG)