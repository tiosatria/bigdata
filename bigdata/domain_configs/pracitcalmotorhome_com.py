
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, Seed
from bigdata.domain_configs import DomainConfigRegistry

PRACTICALMOTORHOME_COM_CONFIG = DomainConfig(
domain="practicalmotorhome.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths="//article[contains(@id,'post')]",
    navigation_xpaths=["//a[@class='next']"],
    max_pages=None,
    custom_parser=None,
    # Content extraction
    title_xpath="//article//h1/text()",
    body_xpath="//div[@class='post-content']",
    tags_xpath="//a[@rel='tag']/text()",
    author_xpath="//[contains(@href,'author')]",
    post_date_xpath="//time/text()",
    # Metadata
    lang="en",
    active=True,
    notes="",
    domain_type="practical skills",
    subdomain_type="motorhome",
    seeds=[
        Seed(url='https://www.practicalmotorhome.com/advice'),
        Seed(url='https://www.practicalmotorhome.com/advice/buying-selling/buying-guides'),
    ],
    cloudflare_proxy_bypass=True
)

DomainConfigRegistry.register(PRACTICALMOTORHOME_COM_CONFIG)
