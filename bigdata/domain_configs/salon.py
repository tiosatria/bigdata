
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry
from post_process.cleaning_pipeline import CleaningPipeline

SALON_COM_CONFIG = DomainConfig(
    domain="salon.com",
    render_engine=RenderEngine.SCRAPY,
    article_target_xpaths="//div[contains(@class,'article')]",
    navigation_xpaths=["//section[contains(@class,'paging')]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//section[contains(@class,'page-article')]|//article | //div[contains(@class,'article')] | //div[contains(@class,'content')]",
    tags_xpath="//section[@class='article__topics']//a/text()",
    author_xpath="//div[@class='writers']//a/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="lifestyle",
    domain_type='life',
    subdomain_type='culture',
    follow_related_content=False
)

# Auto-register
DomainConfigRegistry.register(SALON_COM_CONFIG)

SEEDS = [
    "https://www.salon.com/category/food",
    "https://www.salon.com/category/science-and-health",
    "https://www.salon.com/category/money",
    "https://www.salon.com/category/culture",
]


# VERY HIGH YIELD BUT NOT RELEVANT, HAVE TO FILTER MORE: https://www.salon.com/archive