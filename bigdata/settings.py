# Scrapy settings for bigdata project - Production Grade
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
from scrapy.settings.default_settings import FEEDS, TELNETCONSOLE_PASSWORD, TELNETCONSOLE_USERNAME
from pathlib import Path
from bigdata.middlewares import ProxyMiddleware, FailedRequestExportMiddleware
from bigdata.pipelines import JSONExportPipeline, TransformCrawlerItemToDailyLifeFormat, CleanedJsonlExportPipeline, CleanHtmlFragmentPipeline
import logging
import scrapy.utils.reactor
import sys

# Use AsyncioSelectorReactor everywhere; on Windows, set Proactor event loop policy to avoid select() FD limits.
import asyncio
if sys.platform.startswith('win'):
    try:
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    except Exception:
        # Fallback silently if policy cannot be set
        pass
scrapy.utils.reactor.install_reactor("twisted.internet.asyncioreactor.AsyncioSelectorReactor")

logging.getLogger("scrapy_user_agents.user_agent_picker").setLevel(logging.ERROR)

BOT_NAME = "Mediapartners-Google"
# USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

SPIDER_MODULES = ["bigdata.spiders"]
NEWSPIDER_MODULE = "bigdata.spiders"

SITE_CONFIG_PATH = Path(__file__).resolve().parent.parent / "site_cfg.json"

# ============================================================================
# REDIS CONFIGURATION
# ============================================================================

# Enables scheduling storing requests queue in redis
# SCHEDULER = "scrapy_redis.scheduler.Scheduler"
# DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RFPDupeFilter"

# SCHEDULER_ORDER = 'DFO'
# SCHEDULER_QUEUE_CLASS = 'scrapy_redis.queue.PriorityQueue'
# SCHEDULER_IDLE_BEFORE_CLOSE = 30
# REDIS_URL = 'redis://127.0.0.1:6379'

DEPTH_PRIORITY = 1
# DUPEFILTER_DEBUG = False
SCHEDULER_DISK_QUEUE = "scrapy.squeues.PickleFifoDiskQueue"
SCHEDULER_MEMORY_QUEUE = "scrapy.squeues.FifoMemoryQueue"
DUPEFILTER_CLASS = "scrapy.dupefilters.RFPDupeFilter"
DEPTH_LIMIT = 0
SCHEDULER_PERSIST = True
SCHEDULER_FLUSH_ON_START = False

# Redis Connection URL
# REDIS_URL = 'redis://100.109.89.55:6379'

# ============================================================================
# ROBOTS.TXT
# ============================================================================
ROBOTSTXT_OBEY = False

# ============================================================================
# RETRY CONFIGURATION
# ============================================================================

RETRY_ENABLED = True
RETRY_TIMES = 3
RETRY_HTTP_CODES = [403, 406, 429, 500, 502, 503, 504, 520, 521, 522, 524, 408, 599, 400]
RETRY_PRIORITY_ADJUST = -5

ITEM_PIPELINES = {
    # CleanHtmlFragmentPipeline: 1,
    JSONExportPipeline: 2,
    # TransformCrawlerItemToDailyLifeFormat: 3,
    # CleanedJsonlExportPipeline: 4
}

# ============================================================================
# CONCURRENT REQUESTS & THROTTLING
# ============================================================================
# CONCURRENT_REQUESTS = 1536
CONCURRENT_REQUESTS = 256
CONCURRENT_REQUESTS_PER_DOMAIN = 24
CONCURRENT_ITEMS = 1024
DOWNLOAD_DELAY = 0
RANDOMIZE_DOWNLOAD_DELAY = False

# Disable cookies to reduce memory usage (enable if needed)
COOKIES_ENABLED = True

# ============================================================================
# MEMORY TUNING
# ============================================================================
# MEMUSAGE_ENABLED = True
# MEMUSAGE_LIMIT_MB = 0  # Disable memory limit (0 = unlimited)
# MEMUSAGE_WARNING_MB = 0  # Disable memory w

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


# 'Accept-Encoding': 'identity',
# 'Accept-Encoding': 'gzip, deflate, br',
# 'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
# 'Accept-Language': 'en-US,en;q=0.5',

DEFAULT_REQUEST_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.5',
    'Accept-Encoding': 'gzip, deflate, br',
    'Connection': 'keep-alive',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
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
PLAYWRIGHT_MAX_CONTEXTS = 2048
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
    # 'scrapy.downloadermiddlewares.httpcompression.HttpCompressionMiddleware': None,
    # Proxy setup: custom first, then Scrapy's built-in applies it
    ProxyMiddleware: 350,
    'scrapy.downloadermiddlewares.httpproxy.HttpProxyMiddleware': 400,
    # User agent randomization
    'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 500,
    FailedRequestExportMiddleware: 543
}

# ============================================================================
# ITEM PIPELINES
# ============================================================================

LOG_ENABLED = True
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_ENCODING = 'utf-8'
LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'


HTTPCACHE_ENABLED = False
DNSCACHE_ENABLED = True
DOWNLOAD_TIMEOUT = 120
DNS_TIMEOUT = 60

TELNETCONSOLE_USERNAME = 'gringo'
TELNETCONSOLE_PASSWORD = "gringo"

# ============================================================================
# EXTENSIONS
# ============================================================================

EXTENSIONS = {
    'scrapy.extensions.telnet.TelnetConsole': 100,
    # 'scrapy.extensions.memusage.MemoryUsage': 100,
    'scrapy.extensions.logstats.LogStats': 200,
}

# Log stats every 60 seconds
LOGSTATS_INTERVAL = 30

PIPELINE_BUFFER_SIZE = 10000
PIPELINE_FLUSH_INTERVAL = 60

COMPRESSION_ENABLED = True

# Disable referrer header to avoid tracking
REFERER_ENABLED = True

# STATS_CLASS = 'scrapy.statscollectors.MemoryStatsCollector'