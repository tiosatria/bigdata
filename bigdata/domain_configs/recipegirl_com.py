
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry
from post_process.cleaning_pipeline import CleaningPipeline, HtmlCleaner

RECIPEGIRL_COM_CONFIG = DomainConfig(
    domain="recipegirl.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//article[@class='post-summary']",
    ],
    navigation_xpaths=[
        "//li[@class='pagination-next']"
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article[contains(@class,'content-body')]",
    tags_xpath="//p[@id='breadcrumbs']/span/span/a/text()",
    author_xpath="//p[@class='entry-author']/a/text()",
    post_date_xpath="//p[@class='post-date']/text()",
    # Metadata
    lang="en",
    active=True,
    notes="",
    cleaning_pipelines=CleaningPipeline(
        text_cleaners=[HtmlCleaner(include_image=True)]
    ),
    domain_type='food',
    subdomain_type='recipes',
    follow_related_content=True
)

# Auto-register
DomainConfigRegistry.register(RECIPEGIRL_COM_CONFIG)