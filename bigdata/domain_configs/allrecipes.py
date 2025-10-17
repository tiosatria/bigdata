
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry
from post_process.cleaning_pipeline import CleaningPipeline, HtmlCleaner

ALLRECIPES_COM_CONFIG = DomainConfig(
    domain="allrecipes.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//a[contains(@id,'mntl-card-list-items')]"],

    navigation_xpaths=[
        "//a[@class='gnp-page-nav__button']",
        "//ul[@class='loc mntl-link-list']"
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//ul[contains(@id,'breadcrumbs')]/a/span/text()",
    author_xpath="//a[@class='mntl-attribution__item-name']/text()",
    post_date_xpath="//div[@class='mntl-attribution__item-date']/text()",
    # Metadata
    lang="en",
    active=True,
    notes="",
    cleaning_pipelines=CleaningPipeline(
        text_cleaners=[HtmlCleaner(include_image=True)]
    ),domain_type='food', subdomain_type='recipes'
)

# Auto-register
DomainConfigRegistry.register(ALLRECIPES_COM_CONFIG)