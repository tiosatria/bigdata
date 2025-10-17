
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry
from post_process.cleaning_pipeline import CleaningPipeline, HtmlCleaner

RECIPES_NET_CONFIG = DomainConfig(
    domain="recipes.net",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@class='col-sm-6 col-md-4 col-lg-n25 d-flex flex-column p-3']",
        "//div[@class='col-md-4 col-lg-4 mb-3 px-0 pb-2']"
    ],
    navigation_xpaths=[
        "//link[@rel='next']",
        "//a[contains(@class,'load-more')]",
        "//a[contains(@href,'resources')]",
        "//div[@class='tag-list-container']",
        "//div[@class='col-6 col-md-4 col-lg-2 p-3']",
        "//nav[@class='top-main-menu']//a[@data-wpel-link='internal']"
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@class='body-copy'] "
               "| //div[contains(@id,'recipe-container')] "
               "| //div[@class='align-items-center d-flex pt-2 pb-5']",
    tags_xpath="//a[contains(@class,'badge')]/text() "
               "| //div[@id='breadcrumb-navigation']/ul/li/a[@data-wpel-link='internal']/text() "
               "| //div[@id='breadcrumb-navigation']/ul/li/text()",
    post_date_xpath="//small/em/text()",
    # Metadata
    lang="en",
    active=True,
    notes="",cleaning_pipelines=CleaningPipeline(
        text_cleaners=[HtmlCleaner(include_image=True)]
    )
)

# Auto-register
DomainConfigRegistry.register(RECIPES_NET_CONFIG)