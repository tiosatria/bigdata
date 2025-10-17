
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

SITE_DOM_CONFIG = DomainConfig(
domain="example.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//article"],
    navigation_xpaths=["//div[@class='page-right-side']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//ul[@class='breadcrumbs']/li/a/text()",
    author_xpath="//a[@class='byline-author']/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=False,
    notes="",
    domain_type="",
    subdomain_type="",
    seeds=[
        Seed(url="")
    ]
)

# DomainConfigRegistry.register(SITE_DOM)
