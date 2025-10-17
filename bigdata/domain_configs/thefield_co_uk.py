

from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

THEFIELD_CO_UK_CONFIG = DomainConfig(
domain="thefield.co.uk",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//article[@role='article']",
    ],
    navigation_xpaths=["//nav[@class='paginate']//a[@rel='next']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//article//h1/text()",
    body_xpath="//div[@class='entry-content']",
    tags_xpath="//div[@class='tags']//a[@rel='tag']/text()",
    author_xpath="//span[contains(@class,'author')]/a/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="",
    seeds=[
        Seed(url='https://www.thefield.co.uk/food'),
        Seed(url='https://www.thefield.co.uk/shooting'),
        Seed(url='https://www.thefield.co.uk/hunting'),
        Seed(url='https://www.thefield.co.uk/gundogs'),
        Seed(url='https://www.thefield.co.uk/fishing'),
        Seed(url='https://www.thefield.co.uk/country-house'),
        Seed(url='https://www.thefield.co.uk/country-house'),
        Seed(url='https://www.thefield.co.uk/gardens'),
        Seed(url='https://www.thefield.co.uk/property-country-house'),
    ],
    domain_type='daily-life',
    subdomain_type='guides', follow_related_content=False
)

DomainConfigRegistry.register(THEFIELD_CO_UK_CONFIG)
