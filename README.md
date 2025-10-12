# Production-Grade Web Scraper

A robust, scalable web scraping system built with Scrapy and Redis, designed to handle edge cases, bot protection, and high-volume data extraction.

## 🚀 Features

### Core Capabilities
- **Multi-domain scraping** with per-domain configuration
- **Redis-based distributed crawling** for scalability
- **Automatic retry with exponential backoff**
- **Bot protection detection and handling**
- **Proxy rotation** with multiple strategies
- **Playwright integration** for JavaScript-heavy sites
- **Comprehensive error handling and logging**
- **Content validation and cleaning**
- **Automatic configuration testing**

### Edge Case Handling
- ✅ Missing pagination (continues without errors)
- ✅ 403/429 responses (re-queues with alerts)
- ✅ Bot protection detection (CAPTCHA, Cloudflare)
- ✅ Proxy failures and rotation
- ✅ Timeout and connection errors
- ✅ Empty or invalid responses
- ✅ Rate limiting compliance

## 📋 Prerequisites

```bash
# Python 3.8+
pip install scrapy scrapy-redis scrapy-playwright playwright lxml click requests redis

# Install Playwright browsers
playwright install chromium
```

## 🔧 Configuration

### 1. Redis Setup

Update `settings.py` with your Redis connection:

```python
REDIS_URL = 'redis://your-redis-host:6379'
```

### 2. Add a Domain Configuration

#### Interactive Mode (Recommended)
```bash
python cli.py add example.com --interactive
```

This will guide you through:
- Required fields (title, body, article links XPath)
- Optional fields (author, tags, dates)
- Rendering engine (Scrapy or Playwright)
- Proxy configuration
- Bot protection settings
- Rate limiting

#### Quick Template Mode
```bash
python cli.py add example.com
# Edit the generated file: domain_configs/example_com.py
```

### 3. Test Configuration

```bash
# Test a specific domain
python cli.py test example.com --verbose

# Test with specific URL
python cli.py test example.com --url https://example.com/article

# Test all domains
python cli.py test-all --verbose
```

## 🎯 CLI Commands

### Domain Management

```bash
# List all domains
python cli.py list

# Validate configuration
python cli.py validate example.com

# Edit configuration
python cli.py edit example.com

# Delete configuration
python cli.py delete example.com

# Toggle active status
python cli.py toggle example.com --active
python cli.py toggle example.com --inactive
```

### Testing

```bash
# Test single domain
python cli.py test example.com

# Test all domains
python cli.py test-all

# Verbose output
python cli.py test example.com -v
```

## 🏃 Running the Spider

### 1. Add Start URLs to Redis

```bash
redis-cli LPUSH article:start_urls "https://example.com/articles"
```

Or using Python:
```python
import redis
r = redis.from_url('redis://localhost:6379')
r.lpush('article:start_urls', 'https://example.com/articles')
```

### 2. Start the Spider

```bash
scrapy crawl article
```

### 3. Monitor Progress

```bash
# Watch Redis queue
redis-cli LLEN article:start_urls

# Watch scraped items
redis-cli LLEN article:items

# Check logs
tail -f scrapy.log
```

## 📊 Configuration Options

### Domain Configuration Structure

```python
DomainConfig(
    domain="example.com",
    
    # Rendering
    render_engine=RenderEngine.SCRAPY,  # or PLAYWRIGHT
    
    # Navigation
    article_links_xpath="//article//a/@href",
    pagination_xpath="//a[@rel='next']/@href",
    max_pages=10,  # Optional limit
    
    # Content Extraction (Required)
    title_xpath="//h1/text()",
    body_xpath="//article",
    
    # Optional Extraction
    author_xpath="//span[@class='author']/text()",
    tags_xpath="//a[@rel='tag']/text()",
    post_date_xpath="//time/@datetime",
    post_date_format="%Y-%m-%d",
    
    # Exclusions
    exclude_xpaths=[
        "//div[@class='ads']",
        "//aside"
    ],
    
    # Network Settings
    download_delay=1.0,
    concurrent_requests=2,
    
    # Proxy Configuration
    proxy_config=ProxyConfig(
        enabled=True,
        proxy_list=[
            "http://proxy1.com:8080",
            "http://proxy2.com:8080"
        ],
        rotation_strategy="round_robin"  # round_robin, random, sticky
    ),
    
    # Retry Configuration
    retry_config=RetryConfig(
        max_retries=5,
        retry_http_codes=[403, 429, 500, 502, 503, 504],
        backoff_factor=2.0,
        priority_boost=10
    ),
    
    # Bot Protection
    bot_protection=BotProtectionConfig(
        enabled=True,
        use_stealth_mode=True,
        wait_for_selectors=["#content"]
    ),
    
    # Metadata
    lang="en",
    active=True,
    notes="Configuration notes"
)
```

## 🛡️ Error Handling

### Automatic Retry System

The spider automatically handles:

1. **HTTP Errors** (403, 429, 500, 502, 503, 504)
   - Exponential backoff
   - Priority boost for retries
   - Critical alerts for 403/429

2. **Network Errors**
   - Timeouts
   - Connection failures
   - DNS errors

3. **Bot Protection**
   - CAPTCHA detection
   - Cloudflare challenges
   - Rate limiting

### Alert System

Critical issues trigger alerts:

```
🚨 IMMEDIATE ATTENTION REQUIRED 🚨
Domain: example.com
URL: https://example.com/page
Status: 403 Forbidden
Possible bot detection or IP ban
Request has been re-queued for retry
```

## 📈 Monitoring

### Built-in Statistics

The spider tracks:
- Requests per domain
- Success/failure rates
- Retry counts
- Bot protection hits
- Response times

### Log Levels

```python
# In settings.py
LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
```

### Memory Monitoring

```python
MEMUSAGE_LIMIT_MB = 2048  # Stop if exceeds 2GB
MEMUSAGE_WARNING_MB = 1024  # Warning at 1GB
```

## 🔄 Proxy Management

### Rotation Strategies

1. **Round Robin**: Cycles through proxies sequentially
2. **Random**: Selects random proxy for each request
3. **Sticky**: Uses same proxy for entire domain

### Proxy Failure Tracking

The system automatically:
- Tracks proxy failures
- Rotates to next proxy after 3 failures
- Logs proxy performance

## 🎭 Playwright Mode

For JavaScript-heavy sites:

```python
render_engine=RenderEngine.PLAYWRIGHT
```

Features:
- Headless browser
- JavaScript execution
- Wait for selectors
- Stealth mode (anti-detection)
- Resource blocking (images, CSS)

## 📦 Data Pipelines

### Available Pipelines

1. **ValidationPipeline**: Validates required fields
2. **CleaningPipeline**: Cleans and normalizes content
3. **DeduplicationPipeline**: Removes duplicates
4. **EnrichmentPipeline**: Adds metadata
5. **RedisPipeline**: Stores in Redis
6. **JSONExportPipeline**: Exports to JSON files
7. **DatabasePipeline**: Saves to database (customize)

### Enable Pipelines

```python
# In settings.py
ITEM_PIPELINES = {
    'bigdata.pipelines.ValidationPipeline': 100,
    'bigdata.pipelines.CleaningPipeline': 200,
    'bigdata.pipelines.DeduplicationPipeline': 300,
    'bigdata.pipelines.EnrichmentPipeline': 400,
    'bigdata.pipelines.JSONExportPipeline': 500,
    'bigdata.pipelines.StatisticsPipeline': 900,
}
```

## 🚦 Production Deployment

### 1. Environment Setup

```bash
# Set environment variables
export REDIS_URL="redis://production-redis:6379"
export LOG_LEVEL="INFO"
export MEMUSAGE_LIMIT_MB=2048
```

### 2. Run as Service

```bash
# Using systemd
sudo systemctl start scrapy-spider
sudo systemctl enable scrapy-spider
```

### 3. Monitoring

```bash
# Check logs
journalctl -u scrapy-spider -f

# Monitor Redis
redis-cli --stat

# Check memory usage
ps aux | grep scrapy
```

### 4. Scaling

Run multiple spider instances:

```bash
# Instance 1
scrapy crawl article

# Instance 2 (on different server)
scrapy crawl article

# They'll share the same Redis queue
```

## 🐛 Troubleshooting

### Issue: No articles found

```bash
# Test XPath selectors
python cli.py test example.com --verbose
```

### Issue: 403 Errors

1. Enable Playwright: `render_engine=RenderEngine.PLAYWRIGHT`
2. Add proxies: Configure `proxy_config`
3. Check `bot_protection` settings

### Issue: Slow scraping

1. Increase `CONCURRENT_REQUESTS_PER_DOMAIN`
2. Decrease `DOWNLOAD_DELAY`
3. Adjust `AUTOTHROTTLE_TARGET_CONCURRENCY`

### Issue: Memory usage

1. Reduce `CONCURRENT_REQUESTS`
2. Enable `HTTPCACHE_ENABLED=False`
3. Set `MEMUSAGE_LIMIT_MB`

## 📝 Best Practices

1. **Always test configurations** before production
2. **Start with conservative rate limits**
3. **Monitor logs for bot detection**
4. **Use Playwright only when necessary** (resource intensive)
5. **Implement proper error notifications**
6. **Regular proxy rotation**
7. **Respect robots.txt** (when appropriate)
8. **Keep configurations updated**

## 🔐 Security Considerations

- Store proxy credentials securely
- Use environment variables for sensitive data
- Rotate proxies regularly
- Monitor for IP bans
- Implement rate limiting
- Use HTTPS when possible

## 📄 License

[Your License Here]

## 🤝 Contributing

[Contributing guidelines]

## 📧 Support

For issues or questions:
- Check logs: `scrapy.log`
- Run tests: `python cli.py test-all`
- Review configuration: `python cli.py validate example.com`