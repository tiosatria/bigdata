
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

RELUCTANTGOURMET_COM_CONFIG = DomainConfig(
domain="reluctantgourmet.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths=[
"//article[contains(@class,'post')]",
"//div[@class='e-con-inner']//h1/a",
        "//div[contains(@class,'post__card')]"
    ],
    navigation_xpaths=[
        "//a[contains(@href,'-page')]",
        "//a[@class='page-numbers next']",
                       ],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//div[contains(@class,'post-content')]",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="expert/chef",
    domain_type='expert',
    subdomain_type='food',
    cloudflare_proxy_bypass=True,
    follow_related_content=True,
    seeds=[
        Seed(url="https://www.reluctantgourmet.com/recipes/", bypass_cloudflare=True),
        Seed(url="https://www.reluctantgourmet.com/techniques/", bypass_cloudflare=True),
        Seed(url="https://www.reluctantgourmet.com/planning/", bypass_cloudflare=True),
        Seed(url="https://www.reluctantgourmet.com/ingredients/", bypass_cloudflare=True),
        Seed(url="https://www.reluctantgourmet.com/kitchen-tools/", bypass_cloudflare=True),
        Seed(url="https://www.reluctantgourmet.com/tips/", bypass_cloudflare=True),
        Seed(url="https://www.reluctantgourmet.com/cooking-terms/", bypass_cloudflare=True),
    ]
)

DomainConfigRegistry.register(RELUCTANTGOURMET_COM_CONFIG)
