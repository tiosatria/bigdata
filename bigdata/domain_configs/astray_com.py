from bigdata.domain_configs import DomainConfigRegistry
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine


ASTRAY_COM_CONFIG = DomainConfig(
    domain="astray.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//a[contains(@href, 'recipes') and contains(@href, '?show=')]"
    ]
,
navigation_xpaths = [
    "//a[contains(@href, 'recipes') and not(contains(@href, '?show='))]"
],
    follow_related_content=True,
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@class='grid']",
    exclude_xpaths=["//div[@class='related-recipes']"],
    lang="en",
    active=True,
    notes="food",
    domain_type='food',
    subdomain_type='recipe',
)

DomainConfigRegistry.register(ASTRAY_COM_CONFIG)
