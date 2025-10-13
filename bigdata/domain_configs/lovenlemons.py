"""
Configuration for bonappetit.com
Auto-generated configuration file

Notes: use custom parser
"""

from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

LOVEANDLEMONS_COM_CONFIG = DomainConfig(
    domain="loveandlemons.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//li",
    navigation_xpaths=None,
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/a/text()",
    body_xpath="//div[@class='entry-content entry-content-single']",
    tags_xpath="//div[@class='lnl-tags']/a/text()",
    author_xpath=None,
    post_date_xpath=None,
    
    # Metadata
    lang="en",
    active=True,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(LOVEANDLEMONS_COM_CONFIG)
