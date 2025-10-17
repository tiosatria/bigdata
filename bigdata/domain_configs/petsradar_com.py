
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

PETS_RADAR_COM_CONFIG = DomainConfig(
domain="petsradar.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@class='archive-list']",
        "//section[@class='listing listing--alternate listingdynamic']",
        "//section[@aria-label='articles list']"
    ],
    navigation_xpaths=["//div[@id='archives-filter-sidebar']",
                       "//div[contains(@class, 'flexi-pagination')]//a[contains(@href, 'page') and not(contains(@href, '/archive'))]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//section[@class='content-wrapper'] | //div[@id='article-body']",
    tags_xpath="//nav[@class='breadcrumb']/ol/li/a/text()",
    author_xpath="//div[@class='author__name']",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="FUTURE PLC GROUP", seeds=[
        Seed(url='https://www.petsradar.com/archive/2020/07'),
        Seed(url='https://www.petsradar.com/dogs'),
        Seed(url='https://www.petsradar.com/cats'),
        Seed(url='https://www.petsradar.com/small-pets'),
        Seed(url='https://www.petsradar.com/birds'),
        Seed(url='https://www.petsradar.com/fish'),
        Seed(url='https://www.petsradar.com/pet-tech'),
        Seed(url='https://www.petsradar.com/horses'),
    ], domain_type='pets', subdomain_type='advice'
)

DomainConfigRegistry.register(PETS_RADAR_COM_CONFIG)
