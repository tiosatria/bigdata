
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

GOODTO_COM_CONFIG = DomainConfig(
domain="goodto.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@id='archives-filter']",
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
        Seed(url='https://www.goodto.com/archive/2002/03'),
        Seed(url='https://www.goodto.com/news'),
        Seed(url='https://www.goodto.com/family'),
        Seed(url='https://www.goodto.com/wellbeing/relationships'),
        Seed(url='https://www.goodto.com/wellbeing'),
        Seed(url='https://www.goodto.com/food'),
        Seed(url='https://www.goodto.com/tag/where-to-buy'),
        Seed(url='https://www.goodto.com/family/toys'),
        Seed(url='https://www.goodto.com/tag/family-finance'),
    ], domain_type='parenthood', subdomain_type='advice'
)

DomainConfigRegistry.register(GOODTO_COM_CONFIG)
