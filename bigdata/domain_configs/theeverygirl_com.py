"""
Configuration for theeverygirl.com
Auto-generated configuration file

Notes: html
"""

from bigdata.domain_configs.domain_config import DomainConfig,RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

THEEVERYGIRL_COM_CONFIG = DomainConfig(
    domain="theeverygirl.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@class='grid-item']"
    ],
    navigation_xpaths=[
        "//div[@class='more']"
    ],
    max_pages=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//div[@class='post-intro__category meta']/a/text()",
    author_xpath="//div[@class='post-intro__writer']//a/text()",
    post_date_xpath="//time[@class='post-intro__date meta']/text()",
    # Metadata
    lang="en",
    active=True,
    notes="html"
)

# Auto-register
DomainConfigRegistry.register(THEEVERYGIRL_COM_CONFIG)
