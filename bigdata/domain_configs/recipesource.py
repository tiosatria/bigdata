from bigdata.domain_configs import DomainConfigRegistry
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine


RECIPESOURCE_COM_CONFIG = DomainConfig(
    domain="recipesource.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//a[contains(@href,'.html')]"
    ],
    navigation_xpaths=["//a[not(contains(@href, '.html'))]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//span[@class='topbar-title']/b/text()",
    body_xpath="//pre",
    tags_xpath="//span[@class='topbar-loc']/a[not(contains(@rel,'home'))]",
    lang="en",
    active=True,
    notes="classic site",
    domain_type='food',
    subdomain_type='recipe',
    follow_related_content=True
)

DomainConfigRegistry.register(RECIPESOURCE_COM_CONFIG)
