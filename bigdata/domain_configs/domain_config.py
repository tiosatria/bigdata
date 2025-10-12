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
class ProxyConfig:
    """Proxy configuration"""
    enabled: bool = False
    proxy_list: List[str] = field(default_factory=list)
    rotation_strategy: str = "round_robin"  # round_robin, random, sticky


@dataclass
class RetryConfig:
    """Retry configuration for failed requests"""
    max_retries: int = 5
    retry_http_codes: List[int] = field(default_factory=lambda: [403, 429, 500, 502, 503, 504])
    backoff_factor: float = 2.0  # Exponential backoff multiplier
    priority_boost: int = 10  # Priority boost for retried requests


@dataclass
class BotProtectionConfig:
    """Bot protection handling configuration"""
    enabled: bool = True
    captcha_detection_selectors: List[str] = field(default_factory=lambda: [
        "//div[contains(@class,'g-recaptcha')]",
        "//div[contains(@class,'captcha')]",
        "//iframe[contains(@src,'captcha')]",
        "//div[@id='challenge-form']"  # Cloudflare
    ])
    wait_for_selectors: List[str] = field(default_factory=list)
    use_stealth_mode: bool = True


@dataclass
class DomainConfig:
    """Configuration for a single domain"""
    domain: str

    # Rendering engine
    render_engine: RenderEngine = RenderEngine.SCRAPY

    # Navigation rules
    pagination_xpath: Optional[Iterable[str]|str] = None
    article_links_xpath: Optional[Iterable[str]|str] = None
    max_pages: Optional[int] = None  # Limit pagination depth

    # Content extraction (required fields)
    title_xpath: str = "//h1/text()"
    body_xpath: str = "//article | //div[contains(@class,'content')]"

    # Optional content extraction
    tags_xpath: Optional[str] = None
    author_xpath: Optional[str] = None
    post_date_xpath: Optional[str] = None
    post_date_format: Optional[str] = None  # strptime format

    # Cleaning
    exclude_xpaths: List[str] = field(default_factory=list)

    # Custom parsers (for complex cases)
    custom_parser: Optional[str] = None

    # Network configurations
    proxy_config: ProxyConfig = field(default_factory=ProxyConfig)
    retry_config: RetryConfig = field(default_factory=RetryConfig)
    bot_protection: BotProtectionConfig = field(default_factory=BotProtectionConfig)

    # Rate limiting
    download_delay: float = 1.0
    concurrent_requests: int = 2

    # Playwright specific
    playwright_wait_until: str = "networkidle"  # load, domcontentloaded, networkidle
    playwright_timeout: int = 30000

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

        if not self.article_links_xpath:
            errors.append("Article links XPath is required")

        if self.proxy_config.enabled and not self.proxy_config.proxy_list:
            errors.append("Proxy enabled but no proxy list provided")

        return len(errors) == 0, errors

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization"""
        return {
            'domain': self.domain,
            'render_engine': self.render_engine.value,
            'pagination_xpath': self.pagination_xpath,
            'article_links_xpath': self.article_links_xpath,
            'max_pages': self.max_pages,
            'title_xpath': self.title_xpath,
            'body_xpath': self.body_xpath,
            'tags_xpath': self.tags_xpath,
            'author_xpath': self.author_xpath,
            'post_date_xpath': self.post_date_xpath,
            'post_date_format': self.post_date_format,
            'exclude_xpaths': [x for x in self.exclude_xpaths if x not in OBVIOUS_EXCLUDES],
            'custom_parser': self.custom_parser,
            'download_delay': self.download_delay,
            'concurrent_requests': self.concurrent_requests,
            'playwright_wait_until': self.playwright_wait_until,
            'playwright_timeout': self.playwright_timeout,
            'lang': self.lang,
            'active': self.active,
            'notes': self.notes,
            'proxy_config': {
                'enabled': self.proxy_config.enabled,
                'proxy_list': self.proxy_config.proxy_list,
                'rotation_strategy': self.proxy_config.rotation_strategy
            },
            'retry_config': {
                'max_retries': self.retry_config.max_retries,
                'retry_http_codes': self.retry_config.retry_http_codes,
                'backoff_factor': self.retry_config.backoff_factor,
                'priority_boost': self.retry_config.priority_boost
            },
            'bot_protection': {
                'enabled': self.bot_protection.enabled,
                'captcha_detection_selectors': self.bot_protection.captcha_detection_selectors,
                'wait_for_selectors': self.bot_protection.wait_for_selectors,
                'use_stealth_mode': self.bot_protection.use_stealth_mode
            }
        }