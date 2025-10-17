
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

JOYOFBAKING_COM_CONFIG = DomainConfig(
domain="joyofbaking.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths="//td/a",
    navigation_xpaths=["//a[contains(@href,'RecipeIndex')]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1//font/text()",
    body_xpath="//body",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="legacy sites",
    domain_type='food', subdomain_type='recipes',seeds=[
        Seed(url='https://www.joyofbaking.com/RecipeIndex.html')
    ]
)

DomainConfigRegistry.register(JOYOFBAKING_COM_CONFIG)
