# Scrapy settings for bigdata project - Production Grade
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
from scrapy.settings.default_settings import FEEDS, TELNETCONSOLE_PASSWORD, TELNETCONSOLE_USERNAME

from bigdata.middlewares import ProxyMiddleware, FailedRequestExportMiddleware
from bigdata.pipelines import JSONExportPipeline
import logging
import scrapy.utils.reactor
scrapy.utils.reactor.install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

logging.getLogger("scrapy_user_agents.user_agent_picker").setLevel(logging.ERROR)

BOT_NAME = "google"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

SPIDER_MODULES = ["bigdata.spiders"]
NEWSPIDER_MODULE = "bigdata.spiders"

REQUEST_FINGERPRINTER_IMPLEMENTATION = "2.7"

# ============================================================================
# REDIS CONFIGURATION
# ============================================================================

# Enables scheduling storing requests queue in redis
SCHEDULER = "scrapy_redis.scheduler.Scheduler"
# SCHEDULER_ORDER = 'DFO'
SCHEDULER_ORDER = 'BFO'
SCHEDULER_PERSIST = True
SCHEDULER_QUEUE_CLASS = 'scrapy_redis.queue.SpiderPriorityQueue'
DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RFPDupeFilter"
# SCHEDULER_IDLE_BEFORE_CLOSE = 60

# Redis Connection URL
# REDIS_URL = 'redis://100.109.89.55:6379'

REDIS_URL = 'redis://127.0.0.1:6379'

# ============================================================================
# ROBOTS.TXT
# ============================================================================
ROBOTSTXT_OBEY = False

# ============================================================================
# RETRY CONFIGURATION
# ============================================================================

RETRY_ENABLED = True
RETRY_TIMES = 4
RETRY_HTTP_CODES = [403, 429, 500, 502, 503, 504, 520, 522, 524, 408, 599]
RETRY_PRIORITY_ADJUST = -5

# ============================================================================
# CONCURRENT REQUESTS & THROTTLING
# ============================================================================
# CONCURRENT_REQUESTS = 1536
CONCURRENT_REQUESTS = 256
CONCURRENT_REQUESTS_PER_DOMAIN = 12
CONCURRENT_ITEMS = 2000
DOWNLOAD_DELAY = 0
RANDOMIZE_DOWNLOAD_DELAY = False

# Disable cookies to reduce memory usage (enable if needed)
COOKIES_ENABLED = True

# ============================================================================
# MEMORY TUNING
# ============================================================================
MEMUSAGE_ENABLED = True
MEMUSAGE_LIMIT_MB = 0  # Disable memory limit (0 = unlimited)
MEMUSAGE_WARNING_MB = 0  # Disable memory w

# ============================================================================
# AUTOTHROTTLE CONFIGURATION
# ============================================================================

AUTOTHROTTLE_ENABLED = False
# AUTOTHROTTLE_START_DELAY = 0.5
# AUTOTHROTTLE_MAX_DELAY = 10
# AUTOTHROTTLE_TARGET_CONCURRENCY = 24
# AUTOTHROTTLE_DEBUG = False

# ============================================================================
# REQUEST HEADERS
# ============================================================================

DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'none',
    'Cache-Control': 'max-age=0',
}

# ============================================================================
# PLAYWRIGHT CONFIGURATION
# ============================================================================

DOWNLOAD_HANDLERS = {
    "http": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
    "https": "scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler",
}

PLAYWRIGHT_BROWSER_TYPE = "chromium"
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 60000

PLAYWRIGHT_LAUNCH_OPTIONS = {
    "headless": True,  # Set to True for production
    "args": [
        "--disable-blink-features=AutomationControlled",
        "--disable-dev-shm-usage",
        "--no-sandbox",
        "--disable-setuid-sandbox",
        "--disable-web-security",
        "--disable-features=IsolateOrigins,site-per-process",
        "--disable-images",
        "--disable-plugins",
        "--disable-extensions",
        "--blink-settings=imagesEnabled=false",
        "--no-first-run",
        "--disable-default-apps",
        "--window-size=1920,1080",
    ]
}

# Playwright contexts for parallel processing
PLAYWRIGHT_MAX_CONTEXTS = 64
# PLAYWRIGHT_MAX_CONTEXTS = 4

# Playwright abort unnecessary requests
PLAYWRIGHT_ABORT_REQUEST = lambda request: request.resource_type in ["image", "stylesheet", "font", "media"]


REACTOR_THREADPOOL_MAXSIZE = 256

HTTP2_ENABLED = True

# ============================================================================
# DOWNLOADER MIDDLEWARES
# ============================================================================

DOWNLOADER_MIDDLEWARES = {
    # Disable default user agent middleware
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
    # Proxy setup: custom first, then Scrapy’s built-in applies it
    ProxyMiddleware: 350,
    'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 400,
    # User agent randomization
    'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 500,
    FailedRequestExportMiddleware: 543
}

# ============================================================================
# ITEM PIPELINES
# ============================================================================

ITEM_PIPELINES = {
    # Add your pipelines here
    # 'pipelines.ValidationPipeline': 100,
    # 'pipelines.CleaningPipeline': 200,
    # 'pipelines.DatabasePipeline': 300,
    JSONExportPipeline: 300
}

LOG_ENABLED = True
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_ENCODING = 'utf-8'
LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'

HTTPCACHE_ENABLED = False
DNSCACHE_ENABLED = True
DOWNLOAD_TIMEOUT = 60
DNS_TIMEOUT = 60

TELNETCONSOLE_USERNAME = 'gringo'
TELNETCONSOLE_PASSWORD = "gringo"

# ============================================================================
# EXTENSIONS
# ============================================================================

EXTENSIONS = {
    'scrapy.extensions.telnet.TelnetConsole': 100,  # Disable telnet
    # 'scrapy.extensions.memusage.MemoryUsage': 100,
    'scrapy.extensions.logstats.LogStats': 200,
}

# Log stats every 60 seconds
LOGSTATS_INTERVAL = 60.0

# ============================================================================
# HTTP CACHE (Optional - for development/testing)
# ============================================================================

# Uncomment to enable HTTP caching
# HTTPCACHE_ENABLED = True
# HTTPCACHE_EXPIRATION_SECS = 86400  # 24 hours
# HTTPCACHE_DIR = 'httpcache'
# HTTPCACHE_IGNORE_HTTP_CODES = [403, 429, 500, 502, 503, 504]
# HTTPCACHE_STORAGE = 'scrapy.extensions.httpcache.FilesystemCacheStorage'
# HTTPCACHE_POLICY = 'scrapy.extensions.httpcache.DummyPolicy'

# ============================================================================
# FEED EXPORTS
# ============================================================================

# seperated domain can't handle it
# FEEDS = {
#     'output/%(batch_id)d-data-%(batch_time)s.jsonl': {
#         'format': 'jsonlines',
#         'encoding': 'utf8',
#         'store_empty': False,
#     },
# }

# FEED_EXPORT_BATCH_ITEM_COUNT = 500000

# FEED_EXPORT_ENCODING = "utf-8"

PIPELINE_BUFFER_SIZE = 10000
PIPELINE_FLUSH_INTERVAL = 60

# ============================================================================
# CLOSESPIDER SETTINGS (Safety limits)
# ============================================================================

# Stop spider after certain conditions (uncomment as needed)
# CLOSESPIDER_TIMEOUT = 3600  # Stop after 1 hour
# CLOSESPIDER_ITEMCOUNT = 10000  # Stop after 10k items
# CLOSESPIDER_PAGECOUNT = 50000  # Stop after 50k pages
# CLOSESPIDER_ERRORCOUNT = 100  # Stop after 100 errors

# ============================================================================
# DEPTH LIMIT
# ============================================================================

# DEPTH_LIMIT = 10  # Maximum depth to crawl
# DEPTH_PRIORITY = 1  # Adjust priority by depth
# DEPTH_STATS_VERBOSE = True

# ============================================================================
# DUPLICATION FILTERING
# ============================================================================

# DUPEFILTER_DEBUG = False

# ============================================================================
# REDIRECT SETTINGS
# ============================================================================

REDIRECT_ENABLED = True
REDIRECT_MAX_TIMES = 3

# ============================================================================
# COMPRESSION
# ============================================================================

COMPRESSION_ENABLED = True

# ============================================================================
# ADDITIONAL SECURITY
# ============================================================================

# Disable referrer header to avoid tracking
# REFERER_ENABLED = False


# ============================================================================
# CUSTOM SETTINGS
# ============================================================================

# Domain-specific settings will override these defaults
# Add any additional custom settings here

# Enable stats collection
# STATS_CLASS = 'scrapy.statscollectors.MemoryStatsCollector'