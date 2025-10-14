# https://docs.scrapy.org/en/latest/topics/spider-middleware.html

import json
import os
from datetime import datetime
from pathlib import Path
import logging
from scrapy import signals

class ProxyMiddleware:
    def process_request(self, request, spider):
        request.meta['proxy'] = 'http://icpjabta-rotate:v3cylfcqz2p5@p.webshare.io:80'

    """
    Scrapy Downloader Middleware for exporting failed requests to JSONL
    """
class FailedRequestExportMiddleware:
    """
    Middleware to capture and export failed requests to JSONL files.

    Settings:
        FAILED_REQUESTS_DIR: Directory to store failed request logs (default: 'failed_requests')
        FAILED_REQUESTS_BUFFER_SIZE: Number of failed requests to buffer before writing (default: 100)
        FAILED_REQUESTS_INCLUDE_BODY: Whether to include request body in export (default: False)
        FAILED_REQUESTS_MAX_BODY_SIZE: Max body size to include in bytes (default: 10000)
    """

    def __init__(self, crawler):
        self.crawler = crawler
        self.stats = crawler.stats
        self.logger = logging.getLogger(__name__)

        # Settings
        self.output_dir = crawler.settings.get('FAILED_REQUESTS_DIR', 'failed_requests')
        self.buffer_size = crawler.settings.get('FAILED_REQUESTS_BUFFER_SIZE', 100)
        self.include_body = crawler.settings.get('FAILED_REQUESTS_INCLUDE_BODY', False)
        self.max_body_size = crawler.settings.get('FAILED_REQUESTS_MAX_BODY_SIZE', 10000)

        # Initialize buffer and file
        self.buffer = []
        self.file_handle = None
        self.current_file_path = None

        # Create output directory
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)

    @classmethod
    def from_crawler(cls, crawler):
        middleware = cls(crawler)
        crawler.signals.connect(middleware.spider_opened, signal=signals.spider_opened)
        crawler.signals.connect(middleware.spider_closed, signal=signals.spider_closed)
        return middleware

    def spider_opened(self, spider):
        """Initialize file for this spider"""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"{spider.name}_failed_requests_{timestamp}.jsonl"
        self.current_file_path = os.path.join(self.output_dir, filename)
        self.file_handle = open(self.current_file_path, 'a', encoding='utf-8')
        self.logger.info(f"Failed requests will be logged to: {self.current_file_path}")

    def spider_closed(self, spider):
        """Flush remaining buffer and close file"""
        if self.buffer:
            self._flush_buffer()
        if self.file_handle:
            self.file_handle.close()
            self.logger.info(f"Closed failed requests log: {self.current_file_path}")

    def process_response(self, request, response, spider):
        """Check for HTTP error responses"""
        if response.status >= 400:
            self._log_failed_request(
                request=request,
                response=response,
                reason=f"HTTP {response.status}",
                spider=spider
            )
            self.stats.inc_value('failed_requests_middleware/http_errors')
        return response

    def process_exception(self, request, exception, spider):
        """Capture requests that raised exceptions"""
        self._log_failed_request(
            request=request,
            response=None,
            reason=f"Exception: {exception.__class__.__name__}",
            exception=str(exception),
            spider=spider
        )
        self.stats.inc_value('failed_requests_middleware/exceptions')
        # Return None to let other middlewares handle the exception
        return None

    def _log_failed_request(self, request, response, reason, spider, exception=None):
        """Log failed request details to buffer"""
        failed_request_data = {
            'timestamp': datetime.now().isoformat(),
            'spider': spider.name,
            'url': request.url,
            'method': request.method,
            'reason': reason,
            'headers': dict(request.headers.to_unicode_dict()),
            'meta': self._serialize_meta(request.meta),
            'cookies': request.cookies,
            'priority': request.priority,
            'callback': request.callback.__name__ if request.callback else None,
            'errback': request.errback.__name__ if request.errback else None,
        }

        # Add request body if configured
        if self.include_body and request.body:
            body = request.body
            if len(body) <= self.max_body_size:
                try:
                    failed_request_data['body'] = body.decode('utf-8')
                except UnicodeDecodeError:
                    failed_request_data['body'] = body.hex()
                    failed_request_data['body_encoding'] = 'hex'
            else:
                failed_request_data['body_truncated'] = True
                failed_request_data['body_size'] = len(body)

        # Add response details if available
        if response:
            failed_request_data['response'] = {
                'status': response.status,
                'headers': dict(response.headers.to_unicode_dict()),
                'url': response.url,
            }

        # Add exception details if available
        if exception:
            failed_request_data['exception'] = exception

        # Add to buffer
        self.buffer.append(failed_request_data)

        # Flush if buffer is full
        if len(self.buffer) >= self.buffer_size:
            self._flush_buffer()

    def _flush_buffer(self):
        """Write buffer to file"""
        if not self.buffer:
            return

        try:
            for item in self.buffer:
                json_line = json.dumps(item, ensure_ascii=False)
                self.file_handle.write(json_line + '\n')
            self.file_handle.flush()

            count = len(self.buffer)
            self.buffer.clear()
            self.stats.inc_value('failed_requests_middleware/exported', count)
            self.logger.debug(f"Flushed {count} failed requests to {self.current_file_path}")
        except Exception as e:
            self.logger.error(f"Error flushing failed requests buffer: {e}")

    def _serialize_meta(self, meta):
        """Serialize request meta, handling non-serializable objects"""
        serialized = {}
        for key, value in meta.items():
            # Skip internal Scrapy keys and non-serializable objects
            if key.startswith('_'):
                continue
            try:
                # Test if value is JSON serializable
                json.dumps(value)
                serialized[key] = value
            except (TypeError, ValueError):
                # Store type info for non-serializable values
                serialized[key] = f"<{type(value).__name__}>"
        return serialized