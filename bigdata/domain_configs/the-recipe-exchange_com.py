
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

THERECIPEEXCHANGE_COM_CONFIG = DomainConfig(
domain="the-recipe-exchange.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//a[@class='more-link']"],
    navigation_xpaths=["//div[@class='nav-previous']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//a[@rel='category tag']/text()",
    author_xpath="//span[@itemprop='author']/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="the-recipe-exchange.com group",
    domain_type='food',
    subdomain_type='recipes',
    seeds=[
        Seed(url='http://the-recipe-exchange.com/'),
    ]
)

LOWCARBWAYOFLIFE_THERECIPEEXCHANGE_COM_CONFIG = DomainConfig(
domain="lowcarbwayoflife.the-recipe-exchange.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//a[@class='more-link']"],
    navigation_xpaths=["//div[@class='nav-previous']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//a[@rel='category tag']/text()",
    author_xpath="//span[@itemprop='author']/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="the-recipe-exchange.com group",
    domain_type='food',
    subdomain_type='recipes',
    seeds=[
        Seed(url='http://lowcarbwayoflife.the-recipe-exchange.com/'),
    ]
)

LITTLEBITES_THERECIPEEXCHANGE_COM_CONFIG = DomainConfig(
domain="littlebites.the-recipe-exchange.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//a[@class='more-link']"],
    navigation_xpaths=["//div[@class='nav-previous']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//a[@rel='category tag']/text()",
    author_xpath="//span[@itemprop='author']/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="the-recipe-exchange.com group",
    domain_type='food',
    subdomain_type='recipes',
    seeds=[
        Seed(url='http://littlebites.the-recipe-exchange.com/'),
    ]
)

INSTANTPOTCOOKING_THERECIPEEXCHANGE_COM_CONFIG = DomainConfig(
domain="instantpotcooking.the-recipe-exchange.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//a[@class='more-link']"],
    navigation_xpaths=["//div[@class='nav-previous']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//a[@rel='category tag']/text()",
    author_xpath="//span[@itemprop='author']/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="the-recipe-exchange.com group",
    domain_type='food',
    subdomain_type='recipes',
    seeds=[
        Seed(url='http://instantpotcooking.the-recipe-exchange.com/'),
    ]
)

CROCKPOTCOOKING_THERECIPEEXCHANGE_COM_CONFIG = DomainConfig(
domain="crockpotcooking.the-recipe-exchange.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//a[@class='more-link']"],
    navigation_xpaths=["//div[@class='nav-previous']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//a[@rel='category tag']/text()",
    author_xpath="//span[@itemprop='author']/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="the-recipe-exchange.com group",
    domain_type='food',
    subdomain_type='recipes',
    seeds=[
        Seed(url='http://crockpotcooking.the-recipe-exchange.com/'),
    ]
)

COOKINGFORCHRISTMAS_THERECIPEEXCHANGE_COM_CONFIG = DomainConfig(
domain="cookiesforchristmas.the-recipe-exchange.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//a[@class='more-link']"],
    navigation_xpaths=["//div[@class='nav-previous']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//a[@rel='category tag']/text()",
    author_xpath="//span[@itemprop='author']/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="the-recipe-exchange.com group",
    domain_type='food',
    subdomain_type='recipes',
    seeds=[
        Seed(url='http://cookiesforchristmas.the-recipe-exchange.com/'),
    ]
)

BBQANDGRILLINGRECIPES_THERECIPEEXCHANGE_COM_CONFIG = DomainConfig(
domain="bbqandgrillingrecipes.the-recipe-exchange.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//a[@class='more-link']"],
    navigation_xpaths=["//div[@class='nav-previous']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//a[@rel='category tag']/text()",
    author_xpath="//span[@itemprop='author']/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="the-recipe-exchange.com group",
    domain_type='food',
    subdomain_type='recipes',
    seeds=[
        Seed(url='http://bbqandgrillingrecipes.the-recipe-exchange.com/'),
    ]
)

AIRFRYERRECIPES_THERECIPEEXCHANGE_COM_CONFIG = DomainConfig(
domain="airfryerrecipes.the-recipe-exchange.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=["//a[@class='more-link']"],
    navigation_xpaths=["//div[@class='nav-previous']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    tags_xpath="//a[@rel='category tag']/text()",
    author_xpath="//span[@itemprop='author']/span/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="the-recipe-exchange.com group",
    domain_type='food',
    subdomain_type='recipes',
    seeds=[
        Seed(url='http://airfryerrecipes.the-recipe-exchange.com/'),
    ]
)

DomainConfigRegistry.register(THERECIPEEXCHANGE_COM_CONFIG)
DomainConfigRegistry.register(LOWCARBWAYOFLIFE_THERECIPEEXCHANGE_COM_CONFIG)
DomainConfigRegistry.register(LITTLEBITES_THERECIPEEXCHANGE_COM_CONFIG)
DomainConfigRegistry.register(INSTANTPOTCOOKING_THERECIPEEXCHANGE_COM_CONFIG)
DomainConfigRegistry.register(CROCKPOTCOOKING_THERECIPEEXCHANGE_COM_CONFIG)
DomainConfigRegistry.register(COOKINGFORCHRISTMAS_THERECIPEEXCHANGE_COM_CONFIG)
DomainConfigRegistry.register(BBQANDGRILLINGRECIPES_THERECIPEEXCHANGE_COM_CONFIG)
DomainConfigRegistry.register(AIRFRYERRECIPES_THERECIPEEXCHANGE_COM_CONFIG)
