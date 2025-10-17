
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

SIMPLYGREATRECIPES_COM_CONFIG = DomainConfig(
domain="simplygreatrecipes.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//article", "//a[contains(@href,'/dictionary/dictionary-')]", "//a[contains(@href,'/cooking-basics/')]"],
    navigation_xpaths=["//a[@class='numeric-next-page']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@class='post-content']",
    tags_xpath="//li[@class='category']/span[@class='tasty-recipes-category']/text()",
    author_xpath="//span[@class='tasty-recipes-author-name']/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="cooking exchange successor",
    domain_type='food', subdomain_type='recipes',
    seeds=[
        Seed(url='https://simplygreatrecipes.com/'),
        Seed(url='https://simplygreatrecipes.com/dictionary/'),
        Seed(url='https://simplygreatrecipes.com/cooking-basics/')
    ]
)

DomainConfigRegistry.register(SIMPLYGREATRECIPES_COM_CONFIG)
