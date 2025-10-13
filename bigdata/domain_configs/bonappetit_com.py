"""
Configuration for bonappetit.com
Auto-generated configuration file

Notes: use custom parser
"""

from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

BONAPPETIT_COM_CONFIG = DomainConfig(
    domain="bonappetit.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//div[contains(@class,'StackedRatingsCardWrapper')]",
    navigation_xpaths=[
        "//div[@class='PaginationButtonWrapper-dDcSxp iwYgIg']",
        "//li[@class='NavigationListItemWrapper-cNhNwu dDhky navigation__list-item']"
    ],
    max_pages=None,
    custom_parser="parse_bonappetit",
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//script[@type='application/ld+json']/text()",
    tags_xpath=None,
    author_xpath=None,
    post_date_xpath=None,
    # Metadata
    lang="en",
    active=True,
    notes="use custom parser"
)

# Auto-register
DomainConfigRegistry.register(BONAPPETIT_COM_CONFIG)
