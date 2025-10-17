
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

SHEKNOWS_COM_CONFIG = DomainConfig(
    domain="sheknows.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//article[contains(@class,'o-card')]"
    ],
    deny_urls_regex= [r"/tags/shop/"],
    navigation_xpaths=[
        "//nav[contains(@class,'more-stories')]"
    ],
    max_pages=None,
    custom_parser=None,
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//div[contains(@class,'breadcrumbs')]//li/a/text()",
    author_xpath="//div[contains(@class,'author')]//a/text()",
    post_date_xpath="//time/text()",
    lang="en",
    active=True,
    notes="empowering women",
    domain_type='living',
    subdomain_type='women-empowerment',
)

# Auto-register
DomainConfigRegistry.register(SHEKNOWS_COM_CONFIG)
