# Scrapy settings for bigdata project - Production Grade
#
# For simplicity, this file contains only settings considered important or
# commonly used. You can find more settings consulting the documentation:
#
#     https://docs.scrapy.org/en/latest/topics/settings.html
from bigdata.pipelines import JSONExportPipeline

BOT_NAME = "google"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

SPIDER_MODULES = ["bigdata.spiders"]
NEWSPIDER_MODULE = "bigdata.spiders"

# ============================================================================
# REDIS CONFIGURATION
# ============================================================================

# Enables scheduling storing requests queue in redis
SCHEDULER = "scrapy_redis.scheduler.Scheduler"
# Don't cleanup redis queues, allows to pause/resume crawls
SCHEDULER_PERSIST = True
# Ensure all spiders share same duplicates filter through redis
DUPEFILTER_CLASS = "scrapy_redis.dupefilter.RFPDupeFilter"

# Redis Connection URL
REDIS_URL = 'redis://100.109.89.55:6379'

# Redis key TTL (Time To Live) in seconds - helps prevent memory bloat
REDIS_START_URLS_BATCH_SIZE = 100  # Batch size for reading start URLs
REDIS_ITEMS_KEY = '%(spider)s:items'
REDIS_ITEMS_SERIALIZER = 'json'

# ============================================================================
# ROBOTS.TXT
# ============================================================================
ROBOTSTXT_OBEY = False

# ============================================================================
# RETRY CONFIGURATION
# ============================================================================

RETRY_ENABLED = True
RETRY_TIMES = 6
RETRY_HTTP_CODES = [403, 429, 500, 502, 503, 504, 520, 522, 524, 408, 599]
RETRY_PRIORITY_ADJUST = 10

# ============================================================================
# CONCURRENT REQUESTS & THROTTLING
# ============================================================================

CONCURRENT_REQUESTS = 512
CONCURRENT_REQUESTS_PER_DOMAIN = 2
DOWNLOAD_DELAY = 1

# Disable cookies to reduce memory usage (enable if needed)
COOKIES_ENABLED = True

# ============================================================================
# AUTOTHROTTLE CONFIGURATION
# ============================================================================

AUTOTHROTTLE_ENABLED = True
AUTOTHROTTLE_START_DELAY = 3
AUTOTHROTTLE_MAX_DELAY = 60
AUTOTHROTTLE_TARGET_CONCURRENCY = 2.0
AUTOTHROTTLE_DEBUG = False

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
PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT = 30000

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
# PLAYWRIGHT_MAX_CONTEXTS = 64
# PLAYWRIGHT_MAX_CONTEXTS = 4

# Playwright abort unnecessary requests
PLAYWRIGHT_ABORT_REQUEST = lambda request: request.resource_type in ["image", "stylesheet", "font", "media"]

# ============================================================================
# TWISTED REACTOR
# ============================================================================

TWISTED_REACTOR = "twisted.internet.asyncioreactor.AsyncioSelectorReactor"

# ============================================================================
# DOWNLOADER MIDDLEWARES
# ============================================================================

DOWNLOADER_MIDDLEWARES = {
    # Disable default user agent middleware
    'scrapy.downloadermiddlewares.useragent.UserAgentMiddleware': None,
    # Disable default retry middleware (we use custom)
    'scrapy.downloadermiddlewares.retry.RetryMiddleware': None,
    # Custom middlewares (lower number = higher priority)
    'bigdata.middlewares.ProxyMiddleware': 110,
    'bigdata.middlewares.RequestPriorityMiddleware': 120,
    'bigdata.middlewares.DownloadDelayMiddleware': 200,
    'bigdata.middlewares.SmartRetryMiddleware': 550,
    'bigdata.middlewares.BotProtectionDetectionMiddleware': 560,
    'bigdata.middlewares.ResponseValidationMiddleware': 570,
    'bigdata.middlewares.StatisticsMiddleware': 900,
    # Random user agent (from library)
    'scrapy_user_agents.middlewares.RandomUserAgentMiddleware': 400,
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

# ============================================================================
# LOGGING CONFIGURATION
# ============================================================================

LOG_ENABLED = True
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_ENCODING = 'utf-8'
LOG_FORMAT = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
LOG_DATEFORMAT = '%Y-%m-%d %H:%M:%S'

# Optionally log to file
# LOG_FILE = 'scrapy.log'
# LOG_FILE_APPEND = True

# ============================================================================
# MEMORY & PERFORMANCE
# ============================================================================

# Reduce memory usage
# MEMUSAGE_ENABLED = True
# MEMUSAGE_LIMIT_MB = 2048  # Stop spider if memory exceeds 2GB
# MEMUSAGE_WARNING_MB = 1024  # Warning at 1GB
# MEMUSAGE_NOTIFY_MAIL = []  # Add emails for notifications

# Reduce memory by limiting response size
# DOWNLOAD_MAXSIZE = 10485760  # 10MB max
# DOWNLOAD_WARNSIZE = 5242880  # 5MB warning

# ============================================================================
# TIMEOUTS
# ============================================================================

DOWNLOAD_TIMEOUT = 30
DNS_TIMEOUT = 10

# ============================================================================
# CONTENT VALIDATION
# ============================================================================

MIN_CONTENT_LENGTH = 100  # Minimum content length to consider valid

# ============================================================================
# EXTENSIONS
# ============================================================================

EXTENSIONS = {
    'scrapy.extensions.telnet.TelnetConsole': None,  # Disable telnet
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

FEED_EXPORT_ENCODING = "utf-8"
FEED_EXPORT_INDENT = 2

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

DEPTH_LIMIT = 10  # Maximum depth to crawl
DEPTH_PRIORITY = 1  # Adjust priority by depth
DEPTH_STATS_VERBOSE = True

# ============================================================================
# DUPLICATION FILTERING
# ============================================================================

DUPEFILTER_DEBUG = False

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
REFERER_ENABLED = False

# ============================================================================
# MONITORING & ALERTS (Optional - Add integrations)
# ============================================================================

# Add Sentry for error tracking
# SENTRY_DSN = 'your-sentry-dsn'

# Add Slack/Discord webhook for critical alerts
# SLACK_WEBHOOK_URL = 'your-webhook-url'
# ALERT_ON_403 = True
# ALERT_ON_BOT_DETECTION = True

# ============================================================================
# CUSTOM SETTINGS
# ============================================================================

# Domain-specific settings will override these defaults
# Add any additional custom settings here

# Enable stats collection
STATS_CLASS = 'scrapy.statscollectors.MemoryStatsCollector'