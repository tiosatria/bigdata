
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry
from post_process.cleaning_pipeline import CleaningPipeline, HtmlCleaner

WHITELILY_COM_CONFIG = DomainConfig(

    domain="whitelily.com",

    render_engine=RenderEngine.SCRAPY,
    # Navigation

    article_target_xpaths=[
        "//div[contains(@class,'recipe-tile')]",
    ],

    navigation_xpaths=[
        "//a[contains(@href,'/recipes/')]"
    ],

    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@class='recipe-template__container']",
    tags_xpath="//span[@class='breadcrumbs']/a/text()",
    # Metadata
    lang="en",
    active=True,
    notes="",
    cleaning_pipelines=CleaningPipeline(
        text_cleaners=[HtmlCleaner(include_image=True)]
    ),
    domain_type='food',
    subdomain_type='recipes',
    follow_related_content=True,
    use_proxy=False
)

# Auto-register
DomainConfigRegistry.register(WHITELILY_COM_CONFIG)

SEEDS = [
    "https://www.whitelily.com/recipes/"
]