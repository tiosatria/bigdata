
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry
from post_process.cleaning_pipeline import CleaningPipeline

HUNKER_COM_CONFIG = DomainConfig(
    domain="hunker.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths="//li[@class='article-item']",
    navigation_xpaths=[
        "//a[contains(@href,'/rec/sch')]",
        "//a[@class='lnk b' and b[text()='Next']]",
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//ul[@class='breadcrumbs']/li/a/text()",
    author_xpath="//a[@class='byline-author']/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="daily-life",
    domain_type='how-to',
    subdomain_type='guides'
)

# Auto-register
DomainConfigRegistry.register(HUNKER_COM_CONFIG)

SEEDS = [
    "https://www.hunker.com/category/home-improvement/",
    "https://www.hunker.com/category/design/",
    "https://www.hunker.com/category/cleaning/",
    "https://www.hunker.com/category/garden/",
    "https://www.hunker.com/category/lifestyle/",
    "https://www.hunker.com/category/experts/"
]