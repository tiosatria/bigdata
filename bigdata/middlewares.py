"""
Enhanced middlewares for production-grade scraping
Handles proxies, retries, bot protection, and more
"""

from scrapy import signals
from scrapy.exceptions import NotConfigured, IgnoreRequest
from scrapy.http import HtmlResponse
from urllib.parse import urlparse
import logging
import random
import time


class ProxyMiddleware:
    """Handle proxy rotation per domain configuration"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.proxy_failures = {}  # Track proxy failures
        self.proxy_last_used = {}  # Track when proxy was last used

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        return middleware

    def spider_opened(self, spider):
        self.logger.info('ProxyMiddleware enabled')

    def process_request(self, request, spider):
        """Add proxy to request if configured"""
        # Proxy is already set by spider in _apply_domain_config
        # This middleware tracks failures and rotates if needed

        if 'proxy' in request.meta:
            proxy = request.meta['proxy']

            # Check if proxy has too many recent failures
            failure_count = self.proxy_failures.get(proxy, 0)

            if failure_count >= 3:
                self.logger.warning(f"Proxy {proxy} has {failure_count} failures, may need replacement")

        return None

    def process_response(self, request, response, spider):
        """Track successful proxy usage"""
        if 'proxy' in request.meta:
            proxy = request.meta['proxy']
            # Reset failure count on success
            if response.status < 400:
                self.proxy_failures[proxy] = 0

        return response

    def process_exception(self, request, exception, spider):
        """Handle proxy failures"""
        if 'proxy' in request.meta:
            proxy = request.meta['proxy']
            self.proxy_failures[proxy] = self.proxy_failures.get(proxy, 0) + 1

            self.logger.warning(
                f"Proxy {proxy} failed: {exception} "
                f"(Total failures: {self.proxy_failures[proxy]})"
            )

class SmartRetryMiddleware:
    """Enhanced retry middleware with exponential backoff and priority boost"""

    def __init__(self, settings):
        self.max_retry_times = settings.getint('RETRY_TIMES', 5)
        self.retry_http_codes = set(int(x) for x in settings.getlist('RETRY_HTTP_CODES'))
        self.priority_adjust = settings.getint('RETRY_PRIORITY_ADJUST', 10)
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_crawler(cls, crawler):
        return cls(crawler.settings)

    def process_response(self, request, response, spider):
        """Process response and retry if needed"""
        if request.meta.get('dont_retry', False):
            return response

        # Check if we should retry based on status code
        if response.status in self.retry_http_codes:
            return self._retry(request, response.status, spider) or response

        return response

    def process_exception(self, request, exception, spider):
        """Process exception and retry if needed"""
        if (
                isinstance(exception, self.EXCEPTIONS_TO_RETRY)
                and not request.meta.get('dont_retry', False)
        ):
            return self._retry(request, exception, spider)

    EXCEPTIONS_TO_RETRY = (
        TimeoutError,
        ConnectionRefusedError,
        ConnectionResetError,
    )

    def _retry(self, request, reason, spider):
        """Retry request with exponential backoff"""
        retry_times = request.meta.get('retry_times', 0) + 1
        max_retry_times = request.meta.get('max_retry_times', self.max_retry_times)

        if retry_times <= max_retry_times:
            self.logger.info(
                f"Retrying {request.url} (attempt {retry_times}/{max_retry_times})"
                f" - Reason: {reason}"
            )

            # Create retry request
            retry_req = request.copy()
            retry_req.meta['retry_times'] = retry_times

            # Boost priority for retries
            retry_req.priority = request.priority + self.priority_adjust

            # Add exponential backoff delay
            backoff_factor = request.meta.get('backoff_factor', 2.0)
            delay = min(backoff_factor ** retry_times, 60)  # Max 60 seconds
            retry_req.meta['download_delay'] = delay

            # Log critical retries (403, 429)
            if reason in [403, 429]:
                self.logger.critical(
                    f"🚨 Critical retry needed for {request.url}\n"
                    f"Status: {reason}\n"
                    f"Retry attempt: {retry_times}/{max_retry_times}\n"
                    f"Next attempt in {delay}s"
                )

            return retry_req

        else:
            self.logger.error(
                f"❌ Gave up retrying {request.url} "
                f"after {retry_times} attempts - Reason: {reason}"
            )

            # Re-queue to Redis for manual intervention
            if hasattr(spider, '_requeue_request'):
                spider._requeue_request(request, priority=100)

class BotProtectionDetectionMiddleware:
    """Detect and handle bot protection mechanisms"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

        # Common bot protection indicators
        self.protection_indicators = [
            'captcha',
            'recaptcha',
            'cloudflare',
            'access denied',
            'not a robot',
            'unusual traffic',
            'automated access',
            'security check'
        ]

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_response(self, request, response, spider):
        """Detect bot protection in response"""

        # Check status codes that indicate blocking
        if response.status in [403, 503]:
            self._check_for_protection(request, response, spider)

        # Only check response body for protection indicators if status suggests blocking
        # Don't check on 200 responses unless there are clear blocking indicators
        if isinstance(response, HtmlResponse):
            body_text = response.text.lower()

            # Only check for actual blocking, not just Cloudflare presence
            blocking_indicators = [
                'checking your browser',
                'please wait while we verify',
                'access denied',
                'not a robot',
                'unusual traffic',
                'automated access',
                'security check',
                'captcha',
                'recaptcha'
            ]

            for indicator in blocking_indicators:
                if indicator in body_text:
                    self.logger.critical(
                        f"🤖 Bot protection detected on {request.url}\n"
                        f"Indicator: '{indicator}'\n"
                        f"Status: {response.status}\n"
                        f"Domain: {urlparse(request.url).netloc}"
                    )

                    # Mark for manual review
                    request.meta['bot_protection_detected'] = True

                    # Re-queue with high priority
                    if hasattr(spider, '_requeue_request'):
                        spider._requeue_request(request, priority=90)

                    raise IgnoreRequest("Bot protection detected")

        return response

    def _check_for_protection(self, request, response, spider):
        """Additional checks for protection mechanisms"""

        # Check for Cloudflare
        if 'cf-ray' in response.headers or 'cloudflare' in response.text.lower():
            self.logger.critical(
                f"☁️  Cloudflare protection detected on {request.url}\n"
                f"Status: {response.status}\n"
                f"Consider using Playwright with stealth mode"
            )

        # Check for rate limiting
        if response.status == 429:
            retry_after = response.headers.get('Retry-After', 60)
            self.logger.warning(
                f"⏱️  Rate limited on {request.url}\n"
                f"Retry after: {retry_after} seconds"
            )

class DownloadDelayMiddleware:
    """Enforce domain-specific download delays"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.last_request_time = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        """Enforce download delay per domain"""

        domain = urlparse(request.url).netloc
        delay = request.meta.get('download_delay', 1.0)

        # Check last request time for this domain
        if domain in self.last_request_time:
            elapsed = time.time() - self.last_request_time[domain]

            if elapsed < delay:
                wait_time = delay - elapsed
                self.logger.debug(f"Waiting {wait_time:.2f}s before requesting {domain}")
                time.sleep(wait_time)

        # Update last request time
        self.last_request_time[domain] = time.time()

        return None

class UserAgentRotationMiddleware:
    """Rotate user agents to avoid detection"""

    USER_AGENTS = [
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0',
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15',
        'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    ]

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        """Rotate user agent for each request"""

        # Don't override if custom user agent is set
        if 'User-Agent' not in request.headers:
            user_agent = random.choice(self.USER_AGENTS)
            request.headers['User-Agent'] = user_agent

        return None

class ResponseValidationMiddleware:
    """Validate responses to ensure content quality"""

    def __init__(self, min_content_length=100):
        self.min_content_length = min_content_length
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_crawler(cls, crawler):
        min_length = crawler.settings.getint('MIN_CONTENT_LENGTH', 100)
        return cls(min_content_length=min_length)

    def process_response(self, request, response, spider):
        """Validate response content"""

        # Skip validation for non-HTML responses
        if not isinstance(response, HtmlResponse):
            return response

        # Check content length
        content_length = len(response.text)

        if content_length < self.min_content_length:
            self.logger.warning(
                f"⚠️  Response too short for {request.url}\n"
                f"Content length: {content_length} bytes\n"
                f"Minimum expected: {self.min_content_length} bytes"
            )

            # Optionally retry
            if not request.meta.get('dont_retry', False):
                return self._retry_short_response(request, spider)

        # Check for empty body
        if not response.text.strip():
            self.logger.error(f"❌ Empty response body for {request.url}")

            if not request.meta.get('dont_retry', False):
                return self._retry_short_response(request, spider)

        return response

    def _retry_short_response(self, request, spider):
        """Retry request that returned short/empty content"""

        retry_times = request.meta.get('short_response_retry', 0) + 1

        if retry_times <= 2:  # Max 2 retries for short responses
            self.logger.info(f"Retrying short response: {request.url}")

            retry_req = request.copy()
            retry_req.meta['short_response_retry'] = retry_times
            retry_req.priority = request.priority + 5

            return retry_req

        return None

class StatisticsMiddleware:
    """Track scraping statistics per domain"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.stats = {}

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls()
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def process_response(self, request, response, spider):
        """Track response statistics"""

        domain = urlparse(request.url).netloc

        if domain not in self.stats:
            self.stats[domain] = {
                'total': 0,
                'success': 0,
                'failed': 0,
                'retried': 0,
                'bot_protected': 0
            }

        self.stats[domain]['total'] += 1

        if response.status < 400:
            self.stats[domain]['success'] += 1
        else:
            self.stats[domain]['failed'] += 1

        if request.meta.get('retry_times', 0) > 0:
            self.stats[domain]['retried'] += 1

        if request.meta.get('bot_protection_detected', False):
            self.stats[domain]['bot_protected'] += 1

        return response

    def spider_closed(self, spider):
        """Log statistics when spider closes"""

        self.logger.info("\n" + "=" * 60)
        self.logger.info("📊 SCRAPING STATISTICS")
        self.logger.info("=" * 60)

        for domain, stats in sorted(self.stats.items()):
            success_rate = (stats['success'] / stats['total'] * 100) if stats['total'] > 0 else 0

            self.logger.info(f"\n{domain}:")
            self.logger.info(f"  Total requests: {stats['total']}")
            self.logger.info(f"  Successful: {stats['success']} ({success_rate:.1f}%)")
            self.logger.info(f"  Failed: {stats['failed']}")
            self.logger.info(f"  Retried: {stats['retried']}")

            if stats['bot_protected'] > 0:
                self.logger.warning(f"  ⚠️  Bot protection hits: {stats['bot_protected']}")

        self.logger.info("\n" + "=" * 60)

class RequestPriorityMiddleware:
    """Manage request priorities based on URL type"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_crawler(cls, crawler):
        return cls()

    def process_request(self, request, spider):
        """Adjust request priority based on metadata"""

        # Article pages get higher priority
        if request.meta.get('is_article', False):
            request.priority = 100

        # Pagination gets medium priority
        elif request.meta.get('is_pagination', False):
            request.priority = 50

        # Default priority for other requests
        else:
            request.priority = 10

        return None