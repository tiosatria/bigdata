from dataclasses import dataclass, field
from typing import List, Optional, Iterable
from enum import Enum
from abc import ABC

from scrapy import Spider

from post_process.cleaning_pipeline import CleaningPipeline

class RenderEngine(Enum):
    """Rendering engine options"""
    SCRAPY = "scrapy"
    PLAYWRIGHT = "playwright"

@dataclass
class Seed:

    url: str
    meta: dict = None
    render_engine :RenderEngine = field(default=RenderEngine.SCRAPY)
    bypass_cloudflare : bool = field(default=False)
    use_default_proxy : bool = field(default=True)

    def __post_init__(self):
        if self.meta is None:
            self.meta = {
                'cf-bypass': self.bypass_cloudflare,
                'use_proxy': self.use_default_proxy,
                'playwright': self.render_engine == RenderEngine.PLAYWRIGHT
            }
        else:
            self.meta['cf-bypass'] = self.bypass_cloudflare
            self.meta['use_proxy'] = self.use_default_proxy
            self.meta['playwright'] = self.render_engine == RenderEngine.PLAYWRIGHT.value

    def to_dict(self)-> dict:
        return {
            'url': self.url,
            'meta': self.meta
        }


OBVIOUS_EXCLUDES = [
    "//script",
    "//style",
    "//*[contains(@class,'ads')]",
    "//*[contains(@class,'advertisement')]",
    "//aside",
    "//nav",
    "//footer[contains(@class,'footer')]",
    "//div[contains(@class,'social-share')]",
    "//div[contains(@class,'newsletter')]",
    "//div[contains(@class,'popup')]",
    "//div[contains(@class,'modal')]",
    "//iframe",
    "//*[contains(@class,'related')]",
    "//*[contains(@class,'see-also')]",
]

blacklist_url_regex = [
    r'https?://auth\.[^/]+',
    r'https?://shop\.[^/]+',
    r'https?://product\.[^/]+',
    r'https?://stage\.[^/]+',
    r'https?://staging\.[^/]+',
]

class CustomParser(ABC):

    def parse_item(self, response, config, spider:Spider):
        raise NotImplementedError

@dataclass
class DomainConfig:
    """Configuration for a single domain"""
    domain: str
    site_subdomains: list[str] = field(default_factory=list)

    # Rendering engine
    render_engine: RenderEngine = RenderEngine.SCRAPY

    # Navigation rules
    navigation_xpaths: Optional[Iterable[str] | str] = None
    article_target_xpaths: Optional[Iterable[str] | str] = None
    max_pages: Optional[int] = None  # Limit pagination depth

    # Content extraction (required fields)
    title_xpath: str = "//h1/text()"
    body_xpath: str = "//article | //div[contains(@class,'content')]"

    # Optional content extraction
    tags_xpath: Optional[str] = None
    author_xpath: Optional[str] = None
    post_date_xpath: Optional[str] = None

    use_proxy: bool = True

    follow_related_content:bool = False

    deny_urls_regex: Optional[Iterable[str]|str] = None

    # Cleaning
    exclude_xpaths: List[str] = field(default_factory=list)

    cleaning_pipelines : CleaningPipeline = None

    # Custom parsers (for complex cases)
    custom_parser: Optional[CustomParser] = None

    # Metadata
    lang: str = "en"
    active: bool = True
    notes: str = ""

    seeds: list[str|dict|Seed]=field(default_factory=list)

    cloudflare_proxy_bypass : bool= False

    # Content classification (used for output meta.content_info)
    domain_type: str = "general"  # e.g., news, recipe, tech, etc.
    subdomain_type: Optional[str] = None

    def __post_init__(self):
        # Merge custom excludes with obvious ones
        all_excludes = OBVIOUS_EXCLUDES.copy()
        if self.exclude_xpaths:
            all_excludes.extend(self.exclude_xpaths)
        self.exclude_xpaths = all_excludes

        all_blacklist_url_regex = blacklist_url_regex.copy()
        if self.deny_urls_regex:
            all_blacklist_url_regex.extend(self.deny_urls_regex)
        self.deny_urls_regex = all_blacklist_url_regex

        # Convert string to enum if needed
        if isinstance(self.render_engine, str):
            self.render_engine = RenderEngine(self.render_engine)

    def validate(self) -> tuple[bool, List[str]]:
        """Validate configuration"""
        errors = []

        if not self.domain:
            errors.append("Domain is required")

        if not self.title_xpath:
            errors.append("Title XPath is required")

        if not self.body_xpath:
            errors.append("Body XPath is required")

        if not self.article_target_xpaths:
            errors.append("Article links XPath is required")

        return len(errors) == 0, errors

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'domain': self.domain,
            'render_engine': self.render_engine.value,
            'pagination_xpath': self.navigation_xpaths,
            'article_links_xpath': self.article_target_xpaths,
            'max_pages': self.max_pages,
            'title_xpath': self.title_xpath,
            'body_xpath': self.body_xpath,
            'tags_xpath': self.tags_xpath,
            'author_xpath': self.author_xpath,
            'post_date_xpath': self.post_date_xpath,
            'exclude_xpaths': [x for x in self.exclude_xpaths if x not in OBVIOUS_EXCLUDES],
            'custom_parser': self.custom_parser,
            'deny_urls_regex': self.deny_urls_regex,
            'lang': self.lang,
            'active': self.active,
            'notes': self.notes,
            'cleaning_pipeline': self.cleaning_pipelines,
            'domain_type': self.domain_type,
            'subdomain': self.subdomain_type,
            'cloudflare_proxy_bypass' : self.cloudflare_proxy_bypass,
            'use_proxy': self.use_proxy
        }