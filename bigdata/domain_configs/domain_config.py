from dataclasses import dataclass, field
from typing import List, Optional, Iterable
from enum import Enum

class RenderEngine(Enum):
    """Rendering engine options"""
    SCRAPY = "scrapy"
    PLAYWRIGHT = "playwright"

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

@dataclass
class DomainConfig:
    """Configuration for a single domain"""
    domain: str

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

    # Cleaning
    exclude_xpaths: List[str] = field(default_factory=list)

    # Custom parsers (for complex cases)
    custom_parser: Optional[str] = None
    custom_pagination: Optional[str]= None

    # Metadata
    lang: str = "en"
    active: bool = True
    notes: str = ""

    def __post_init__(self):
        # Merge custom excludes with obvious ones
        all_excludes = OBVIOUS_EXCLUDES.copy()
        if self.exclude_xpaths:
            all_excludes.extend(self.exclude_xpaths)
        self.exclude_xpaths = all_excludes

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
            'post_date_format': self.post_date_format,
            'exclude_xpaths': [x for x in self.exclude_xpaths if x not in OBVIOUS_EXCLUDES],
            'custom_parser': self.custom_parser,
            'lang': self.lang,
            'active': self.active,
            'notes': self.notes,
        }