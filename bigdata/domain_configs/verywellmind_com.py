
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

VERYWELLMIND_COM_CONFIG = DomainConfig(
domain="verywellmind.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
        "//div[contains(@id,'alphabetical-list')]",
        "//a[contains(@data-cta,'Read')]",
        "//div[@class='card__content ']"
    ],
    navigation_xpaths=[
        "//ol[@class='alphabetical-nav-list']",
        ""
    ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//article | //div[contains(@class,'intro')]",
    tags_xpath="//ul[@class='breadcrumbs']/li/a/text()",
    author_xpath="//a[contains(@class,'attribution')]",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="people group inc.",
    domain_type="mind & body",
    subdomain_type="wellness",
    follow_related_content=True,
    seeds=[
        Seed(url="https://www.verywellmind.com/conditions-a-z-4797402"),
        Seed(url="https://www.verywellmind.com/therapy-4581775"),
        Seed(url="https://www.verywellmind.com/living-well-7510832"),
        Seed(url="https://www.verywellmind.com/relationships-4157190"),
        Seed(url="https://www.verywellmind.com/news-latest-research-and-trending-topics-4846421"),
        Seed(url="https://www.verywellmind.com/psychology-4157187"),
        Seed(url="https://www.verywellmind.com/addiction-overview-4581803"),
    ]
)

DomainConfigRegistry.register(VERYWELLMIND_COM_CONFIG)
