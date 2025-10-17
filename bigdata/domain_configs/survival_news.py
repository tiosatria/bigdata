
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine
from bigdata.domain_configs import DomainConfigRegistry

SURVIVAL_NEWS_CONFIG = DomainConfig(
    domain="survival.news",
    render_engine=RenderEngine.SCRAPY,

    # Navigation
    article_target_xpaths="//div[@class='PostsAll']",
    navigation_xpaths="//a[contains(text(),'Next >')]",
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@class='PostArticle']",
    tags_xpath="//a[@rel='tag']/text()",
    author_xpath="//a[@rel='author']/text()",
    post_date_xpath="//span[@class='Date']/text()",
    # Metadata
    lang="en",
    active=True,
    notes="survival news, may need some additional filtering"
)

# Auto-register
DomainConfigRegistry.register(SURVIVAL_NEWS_CONFIG)
