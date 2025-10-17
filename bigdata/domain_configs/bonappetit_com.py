
from bigdata.domain_configs import DomainConfigRegistry
from bigdata.domain_configs.domain_config import DomainConfig, RenderEngine, CustomParser
import datetime
import json

from bigdata.items import ArticleItem


class BonAppetitParser(CustomParser):

    def parse_item(self, response, config, spider):
        title = None
        tags = []
        author = None
        post_date = None
        json_obj = {}  # Initialize to avoid UnboundLocalError in the yield statement

        try:
            # The XPath should select the text content of the script tag
            json_string = response.xpath(config.body_xpath).get()
            json_obj = json.loads(json_string)

            title = json_obj.get("headline")  # "headline" is more specific than "name" or "title"
            tags = json_obj.get("keywords", [])  # .get() with a default value is safer

            # Author is a list of objects, so we access the first item's 'name'
            author_list = json_obj.get("author", [])
            if author_list:
                author = author_list[0].get("name")

            post_date = json_obj.get("datePublished")

        except (json.JSONDecodeError, AttributeError, IndexError) as e:
            spider.logger.error(f"Failed to parse JSON from {response.url}. Error: {e}")

        yield ArticleItem(
            url=response.url,
            source_domain=config.domain,
            title=title,
            tags=tags,
            author=author,
            post_date=post_date,
            body=json_obj,
            body_type="json",
            lang=config.lang,
            timestamp=datetime.datetime.now()
        )

        spider.logger.info(f"✓ Successfully scraped: {title[:50]}... from {config.domain}")


BONAPPETIT_COM_CONFIG = DomainConfig(
    domain="bonappetit.com",
    render_engine=RenderEngine.SCRAPY,
    # Navigation
    article_target_xpaths="//div[contains(@class,'StackedRatingsCardWrapper')]",
    navigation_xpaths=[
        "//div[@class='PaginationButtonWrapper-dDcSxp iwYgIg']",
        "//a[contains(@class,'NavigationInternalLink')]"
    ],
    max_pages=None,
    custom_parser=BonAppetitParser(),
    # Content extraction
    title_xpath="//h1/text()",
    body_xpath="//script[@type='application/ld+json']/text()",
    tags_xpath=None,
    author_xpath=None,
    post_date_xpath=None,
    # Metadata
    lang="en",
    active=True,
    notes="use custom parser"
)

# Auto-register
DomainConfigRegistry.register(BONAPPETIT_COM_CONFIG)
