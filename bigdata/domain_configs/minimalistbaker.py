"""
Configuration for bonappetit.com
Auto-generated configuration file

Notes: use custom parser
"""

from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

MINIMALISTBAKER_COM_CONFIG = DomainConfig(
    domain="minimalistbaker.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//article",
    navigation_xpaths="//li[@class='pagination-next']",
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@class='entry-content']",
    tags_xpath="//a[@rel='category tag']/text()",
    author_xpath=None,
    post_date_xpath=None,
    post_date_format=None,

    # Network settings
    download_delay=0.8,
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
    active=False,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(MINIMALISTBAKER_COM_CONFIG)
