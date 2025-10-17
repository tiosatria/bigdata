
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

HEALTHLINE_COM_CONFIG = DomainConfig(
domain="healthline.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        #a-z lettering dir topics, get only health, for other, we get on the other paths
        "//div[@data-testid='topic-group']//a[contains(@href,'/health/')]",
        #article
        "//li[@class='css-1jqsg45']"
    ],
    navigation_xpaths=[
        # pagination
        "//div[@class='css-2ertad']"
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article",
    author_xpath="//a[@class='byline-author']/text()",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="health",
    domain_type="health & wellness",
    subdomain_type="wellness/disease/prevention",
    seeds=[
        Seed(url='https://www.healthline.com/directory/topics'),
        Seed(url='https://www.healthline.com/directory/drugs-a-z'),
        Seed(url='https://www.healthline.com/directory/diabetesmine'),
        Seed(url='https://www.healthline.com/directory/news'),
        Seed(url='https://www.healthline.com/directory/nutrition'),
        Seed(url='https://www.healthline.com/directory/recent'),
    ]
)

DomainConfigRegistry.register(HEALTHLINE_COM_CONFIG)
