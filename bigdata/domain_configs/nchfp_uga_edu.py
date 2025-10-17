
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

NCHFP_UGA_EDU_CONFIG = DomainConfig(
domain="nchfp.uga.edu",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//a[contains(@href,'/how/') and not(contains(@href,'spanish'))]", "//article"],
    navigation_xpaths=["//a[@class='page-link page-link--next']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h2[@class='section__content-title']/text() | //h2[@class='article__title']/text()",
    body_xpath="//div[@class='section__content'] | //div[@class='article__content']",
    tags_xpath="//*[contains(@class,'breadcrumb')]//li//*/text()",
    # Metadata
    lang="en",
    active=True,
    notes="univ ext",
    seeds=[
        Seed(url='https://nchfp.uga.edu/'),
        Seed(url='https://nchfp.uga.edu/blog')
    ], domain_type='life sustainability',
    subdomain_type='food preservation',
    follow_related_content=True
)

DomainConfigRegistry.register(NCHFP_UGA_EDU_CONFIG)
