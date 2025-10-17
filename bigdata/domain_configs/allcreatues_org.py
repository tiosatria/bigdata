
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

SITE_DOM_CONFIG = DomainConfig(
domain="all-creatures.org",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//div[@class='innertube']//*[contains(@href,'.html')]", "//div[@class='photo-wrapper']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()[2]",
    body_xpath="//div[@class='innertube']",
    # Metadata
    lang="en",
    active=True,
    notes="opinionated sites", seeds=[
        Seed(url='https://all-creatures.org/recipes/index.html'),
        Seed(url='https://all-creatures.org/recipes/special.html'),
        Seed(url='https://all-creatures.org/recipes/u.html'),
    ], domain_type='food', subdomain_type='vegan-food', follow_related_content=True
)



# DomainConfigRegistry.register(SITE_DOM)
