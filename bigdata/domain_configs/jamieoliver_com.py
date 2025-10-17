
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

JAMIEOLIVER_COM_CONFIG = DomainConfig(
domain="jamieoliver.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths="//a[contains(@class,'card--3/4')]",
    navigation_xpaths=["//a[@x-show='canLoadMore']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@class='default__content-wrapper astro-jwirc66j']",
    tags_xpath="//div[contains(@id,'scroller__scroll')]/a/span/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="chef site",
    follow_related_content=True,
    domain_type='chef/expert',
    subdomain_type='recipes',
)

DomainConfigRegistry.register(JAMIEOLIVER_COM_CONFIG)

SEEDS = [
    "https://www.jamieoliver.com/recipes/all",
    "https://www.jamieoliver.com/inspiration",
]
