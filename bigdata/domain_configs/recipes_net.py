
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

RECIPES_NET_CONFIG = DomainConfig(
    domain="recipes.net",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths=[],
    navigation_xpaths=[],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="",
    body_xpath="",
    tags_xpath="",
    author_xpath="",
    post_date_xpath="",
    # Metadata
    lang="en",
    active=True,
    notes=""
)

# Auto-register
DomainConfigRegistry.register(RECIPES_NET_CONFIG)