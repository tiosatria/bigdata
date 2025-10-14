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
    # Metadata
    lang="en",
    active=False,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(MINIMALISTBAKER_COM_CONFIG)
