
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

PARENTS_COM_CONFIG = DomainConfig(
domain="parents.com",
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
    domain_type="parenthood",
    subdomain_type="parenting",
    follow_related_content=True,
    seeds=[
        Seed(url="https://www.parents.com/pregnancy-postpartum-5282488"),
        Seed(url="https://www.parents.com/starting-a-family-5282670"),
        Seed(url="https://www.parents.com/baby-names/"),
        Seed(url="https://www.parents.com/parenting/"),
        Seed(url="https://www.parents.com/lifestyle-5282764"),
        Seed(url="https://www.parents.com/what-to-buy-7507577"),
        Seed(url="https://www.parents.com/news/"),
    ]
)

DomainConfigRegistry.register(PARENTS_COM_CONFIG)
