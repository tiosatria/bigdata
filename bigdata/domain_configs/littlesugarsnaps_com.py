
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

LITTLESUGARSNAPS_COM_CONFIG = DomainConfig(
domain="littlesugarsnaps.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths="//li[@class='listing-item']",
    navigation_xpaths=["//a[contains(@href,'category/')]", "//a[@class='next page-numbers']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//nav[@id='breadcrumbs']/span/span/a/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="", follow_related_content=True, domain_type='food', subdomain_type='recipes',
    seeds=[
        Seed(url='https://www.littlesugarsnaps.com/recipes/')
    ]
)

DomainConfigRegistry.register(LITTLESUGARSNAPS_COM_CONFIG)
