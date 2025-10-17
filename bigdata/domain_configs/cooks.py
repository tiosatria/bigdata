
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry
from post_process.cleaning_pipeline import CleaningPipeline

COOKS_COM_CONFIG = DomainConfig(
    domain="cooks.com",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//a[contains(@href,'recipe')]",
    navigation_xpaths=[
        "//a[contains(@href,'/rec/sch')]",
        "//a[@class='lnk b' and b[text()='Next']]",
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//span[@class='fn']/text()",
    body_xpath="//body",
    tags_xpath="//a[@class='lnk']/text()",
    author_xpath=None,
    post_date_xpath=None,
    # Metadata
    lang="en",
    active=True,
    notes="cooks",
    domain_type='food',
    subdomain_type='recipes',
)

# Auto-register
DomainConfigRegistry.register(COOKS_COM_CONFIG)
