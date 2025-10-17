
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry
from post_process.cleaning_pipeline import CleaningPipeline

TREEHUGGER_COM_CONFIG = DomainConfig(
    domain="treehugger.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//li[contains(@id,'masonry-list')]",
        "//a[contains(@id,'card-list')]",
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[contains(@id,'article-content')] | //article",
    tags_xpath="//ul[contains(@id,'breadcrumb')]//span/text()",
    author_xpath="//a[contains(@class,'attribution')]/text()",
    post_date_xpath="//div[contains(@class,'date')]/text()",
    # Metadata
    lang="en",
    active=True,
    notes="sustainability",
    domain_type='life',
    subdomain_type='sustainability',
)

# Auto-register
DomainConfigRegistry.register(TREEHUGGER_COM_CONFIG)

SEEDS = [
    "https://www.treehugger.com/recycling-and-waste-4846074",
    "https://www.treehugger.com/home-4846063",
    "https://www.treehugger.com/garden-4846054",
    "https://www.treehugger.com/pets-4846034",
    "https://www.treehugger.com/tiny-homes-4846022",
    "https://www.treehugger.com/interior-design-4846021",
    "https://www.treehugger.com/green-design-4846020",
    "https://www.treehugger.com/urban-design-4846018",
    "https://www.treehugger.com/sustainable-fashion-4846014",
    "https://www.treehugger.com/clean-beauty-products-5176151",
    "https://www.treehugger.com/clean-beauty-tips-5176156",
    "https://www.treehugger.com/food-issues-4846044",
    "",
    "",
]