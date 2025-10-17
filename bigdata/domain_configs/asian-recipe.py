
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

ASIANRECIPE_COM_CONFIG = DomainConfig(
domain="asian-recipe.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths="//article",
    navigation_xpaths=["//a[@class='next page-numbers']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//ul[@class='breadcrumbs']/li/a/text()",
    author_xpath="//span[contains(@class,'author')]/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="",
    seeds=[
        Seed(url='https://asian-recipe.com/'),
        Seed(url='https://asian-recipe.com/category/drink'),
        Seed(url='https://asian-recipe.com/category/food-drink'),
        Seed(url='https://asian-recipe.com/category/drink'),
        Seed(url='https://asian-recipe.com/category/drink'),
    ],domain_type='food', subdomain_type='recipes', follow_related_content=True
)

DomainConfigRegistry.register(ASIANRECIPE_COM_CONFIG)
