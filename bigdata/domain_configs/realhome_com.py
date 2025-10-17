
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

REALHOMES_COM_CONFIG = DomainConfig(
domain="realhomes.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@id='archives-filter']//ul[@class='archive__list']",
        "//section[@class='listing listing--alternate listingdynamic']",
    ],
    navigation_xpaths=["//div[@id='archives-filter-sidebar']",
                       "//div[contains(@class, 'flexi-pagination')]//a[contains(@href, 'page') and not(contains(@href, '/archive'))]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@id='article-body']",
    tags_xpath="//nav[@class='breadcrumb']/ol/li/a/text()",
    author_xpath="//div[@class='author__name']",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=False,
    notes="FUTURE PLC GROUP", seeds=[
        Seed(url='https://www.realhomes.com/archive/2013/01'),
        Seed(url='https://www.realhomes.com/cleaning'),
        Seed(url='https://www.realhomes.com/home-improvement'),
        Seed(url='https://www.realhomes.com/interior-design'),
        Seed(url='https://www.realhomes.com/rooms'),
        Seed(url='https://www.realhomes.com/outdoors'),
        Seed(url='https://www.realhomes.com/property'),
        Seed(url='https://www.realhomes.com/home-technology'),
        Seed(url='https://www.realhomes.com/buying-guides'),
    ], domain_type='home', subdomain_type='home-improvement'
)

DomainConfigRegistry.register(REALHOMES_COM_CONFIG)

LIVINGETC_COM_CONFIG = DomainConfig(
domain="livingetc.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@id='archives-filter']//ul[@class='archive__list']",
        "//section[@class='listing listing--alternate listingdynamic']",
    ],
    navigation_xpaths=["//div[@id='archives-filter-sidebar']",
                       "//div[contains(@class, 'flexi-pagination')]//a[contains(@href, 'page') and not(contains(@href, '/archive'))]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@id='article-body']",
    tags_xpath="//nav[@class='breadcrumb']/ol/li/a/text()",
    author_xpath="//div[@class='author__name']",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=False,
    notes="FUTURE PLC GROUP", seeds=[
        Seed(url='https://www.livingetc.com/archive/2017/09'),
        Seed(url='https://www.livingetc.com/design-ideas'),
        Seed(url='https://www.livingetc.com/modern-homes'),
        Seed(url='https://www.livingetc.com/expert-advice'),
        Seed(url='https://www.livingetc.com/outdoor-living'),
        Seed(url='https://www.livingetc.com/lifestyle'),
    ], domain_type='home', subdomain_type='home-improvement'
)

DomainConfigRegistry.register(LIVINGETC_COM_CONFIG)

COUNTRYLIFE_CO_UK_CONFIG = DomainConfig(
domain="countrylife.co.uk",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@id='archives-filter']//ul[@class='archive__list']",
        "//section[@class='listing listing--alternate listingdynamic']",
    ],
    navigation_xpaths=["//div[@id='archives-filter-sidebar']",
                       "//div[contains(@class, 'flexi-pagination')]//a[contains(@href, 'page') and not(contains(@href, '/archive'))]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@id='article-body']",
    tags_xpath="//nav[@class='breadcrumb']/ol/li/a/text()",
    author_xpath="//div[@class='author__name']",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=False,
    notes="FUTURE PLC GROUP", seeds=[
        Seed(url='https://www.countrylife.co.uk/archive/2000/10'),
        Seed(url='https://www.countrylife.co.uk/property'),
        Seed(url='https://www.countrylife.co.uk/interiors'),
        Seed(url='https://www.countrylife.co.uk/gardens'),
        Seed(url='https://www.countrylife.co.uk/luxury'),
        Seed(url='https://www.countrylife.co.uk/out-and-about'),
        Seed(url='https://www.countrylife.co.uk/food-drink'),
        Seed(url='https://www.countrylife.co.uk/nature'),
    ], domain_type='living', subdomain_type='country-style'
)

DomainConfigRegistry.register(COUNTRYLIFE_CO_UK_CONFIG)

WOMENANDHOME_COM_CONFIG = DomainConfig(
domain="womanandhome.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@id='archives-filter']//ul[@class='archive__list']",
        "//section[@class='listing listing--alternate listingdynamic']",
    ],
    navigation_xpaths=["//div[@id='archives-filter-sidebar']",
                       "//div[contains(@class, 'flexi-pagination')]//a[contains(@href, 'page') and not(contains(@href, '/archive'))]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@id='article-body']",
    tags_xpath="//nav[@class='breadcrumb']/ol/li/a/text()",
    author_xpath="//div[@class='author__name']",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=False,
    notes="FUTURE PLC GROUP", seeds=[
        Seed(url='https://www.womanandhome.com/archive/2005/11/'),
        Seed(url='https://www.womanandhome.com/fashion/'),
        Seed(url='https://www.womanandhome.com/beauty/'),
        Seed(url='https://www.womanandhome.com/homes/'),
        Seed(url='https://www.womanandhome.com/health-wellbeing/'),
        Seed(url='https://www.womanandhome.com/buying-guides/'),
        Seed(url='https://www.womanandhome.com/food/'),
    ], domain_type='women', subdomain_type='home'
)

DomainConfigRegistry.register(WOMENANDHOME_COM_CONFIG)

MARIECLAIRE_CO_UK_CONFIG = DomainConfig(
domain="marieclaire.co.uk",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@id='archives-filter']//ul[@class='archive__list']",
        "//section[@class='listing listing--alternate listingdynamic']",
    ],
    navigation_xpaths=["//div[@id='archives-filter-sidebar']",
                       "//div[contains(@class, 'flexi-pagination')]//a[contains(@href, 'page') and not(contains(@href, '/archive'))]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@id='article-body']",
    tags_xpath="//nav[@class='breadcrumb']/ol/li/a/text()",
    author_xpath="//div[@class='author__name']",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=False,
    notes="FUTURE PLC GROUP", seeds=[
        Seed(url='https://www.marieclaire.co.uk/archive/2001/07'),
        Seed(url='https://www.marieclaire.co.uk/fashion/shopping'),
        Seed(url='https://www.marieclaire.co.uk/fashion/watches-jewellery'),
        Seed(url='https://www.marieclaire.co.uk/tag/the-one'),
        Seed(url='https://www.marieclaire.co.uk/beauty/skincare'),
        Seed(url='https://www.marieclaire.co.uk/beauty/make-up'),
        Seed(url='https://www.marieclaire.co.uk/beauty/hair'),
        Seed(url='https://www.marieclaire.co.uk/beauty/fragrance'),
        Seed(url='https://www.marieclaire.co.uk/life/health-fitness'),
        Seed(url='https://www.marieclaire.co.uk/beauty/life'),
        Seed(url='https://www.marieclaire.co.uk/beauty/work'),
    ], domain_type='women', subdomain_type='home'
)

DomainConfigRegistry.register(MARIECLAIRE_CO_UK_CONFIG)

MARIECLAIRE_COM_CONFIG = DomainConfig(
domain="marieclaire.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[@id='archives-filter']//ul[@class='archive__list']",
        "//section[@class='listing listing--alternate listingdynamic']",
    ],
    navigation_xpaths=["//div[@id='archives-filter-sidebar']",
                       "//div[contains(@class, 'flexi-pagination')]//a[contains(@href, 'page') and not(contains(@href, '/archive'))]"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[@id='article-body']",
    tags_xpath="//nav[@class='breadcrumb']/ol/li/a/text()",
    author_xpath="//div[@class='author__name']",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=False,
    notes="FUTURE PLC GROUP", seeds=[
        Seed(url='https://www.marieclaire.com/archive/2002/06/'),
        Seed(url='https://www.marieclaire.com/fashion/'),
        Seed(url='https://www.marieclaire.com/beauty/'),
        Seed(url='https://www.marieclaire.com/career-advice/'),
        Seed(url='https://www.marieclaire.com/health-fitness/'),
        Seed(url='https://www.marieclaire.com/travel/'),
        Seed(url='https://www.marieclaire.com/food-cocktails/'),
        Seed(url='https://www.marieclaire.com/sex-love/'),
    ], domain_type='women', subdomain_type='home'
)

DomainConfigRegistry.register(MARIECLAIRE_COM_CONFIG)

HOMEBUILDING_CO_UK_CONFIG = DomainConfig(
domain="homebuilding.co.uk",
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
        Seed(url='https://www.marieclaire.com/archive/2002/06/'),
        Seed(url='https://www.homebuilding.co.uk/advice'),
        Seed(url='https://www.homebuilding.co.uk/how-to'),
        Seed(url='https://www.homebuilding.co.uk/buying-guides'),
        Seed(url='https://www.homebuilding.co.uk/tag/design-ideas'),
        Seed(url='https://www.homebuilding.co.uk/rooms'),
        Seed(url='https://www.homebuilding.co.uk/eco-homes'),
        Seed(url='https://www.homebuilding.co.uk/outdoors/'),
    ], domain_type='home', subdomain_type='improvement'
)

DomainConfigRegistry.register(HOMEBUILDING_CO_UK_CONFIG)

