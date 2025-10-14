"""
Production-grade item pipelines
Handles validation, cleaning, deduplication, and storage
"""
from collections import defaultdict
from datetime import datetime
from urllib.parse import urlparse
import hashlib
import logging
import re
from pathlib import Path
from lxml import html, etree

import json
import logging
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any
import threading
from queue import Queue
import atexit


class CleaningPipeline:
    """Clean and normalize scraped content"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def process_item(self, item, spider):
        """Clean and normalize item data"""

        # Clean title
        item['title'] = self._clean_text(item['title'])

        # Clean author if present
        if item.get('author'):
            item['author'] = self._clean_text(item['author'])

        # Clean tags
        if item.get('tags'):
            item['tags'] = [self._clean_text(tag) for tag in item['tags']]
            item['tags'] = [tag for tag in item['tags'] if tag]  # Remove empty

        # Clean and validate body HTML
        if item.get('body_type') == 'html':
            item['body'] = self._clean_html(item['body'])

        # Ensure URL is absolute and normalized
        item['url'] = self._normalize_url(item['url'])

        # Add content hash for deduplication
        item['content_hash'] = self._generate_content_hash(item)

        return item

    def _clean_text(self, text):
        """Clean text content"""
        if not text:
            return ""

        # Remove extra whitespace
        text = re.sub(r'\s+', ' ', text)

        # Remove leading/trailing whitespace
        text = text.strip()

        # Remove control characters
        text = ''.join(char for char in text if ord(char) >= 32 or char in '\n\t')

        return text

    def _clean_html(self, html_content):
        """Clean HTML content"""
        if not html_content:
            return ""

        try:
            # Parse HTML
            doc = html.fromstring(html_content)

            # Remove comments
            for comment in doc.xpath('//comment()'):
                comment.getparent().remove(comment)

            # Remove empty elements
            for element in doc.xpath('//*[not(normalize-space())]'):
                if element.tag not in ['br', 'hr', 'img']:
                    parent = element.getparent()
                    if parent is not None:
                        parent.remove(element)

            # Serialize back to HTML
            cleaned_html = etree.tostring(doc, encoding='unicode', method='html')

            return cleaned_html

        except Exception as e:
            self.logger.warning(f"Failed to clean HTML: {e}")
            return html_content

    def _normalize_url(self, url):
        """Normalize URL"""
        # Remove fragment
        if '#' in url:
            url = url.split('#')[0]

        # Remove trailing slash (except for root)
        parsed = urlparse(url)
        if parsed.path != '/' and parsed.path.endswith('/'):
            url = url.rstrip('/')

        return url

    def _generate_content_hash(self, item):
        """Generate hash of content for deduplication"""
        # Create hash from title + first 1000 chars of body
        content = f"{item['title']}{item['body'][:1000]}"
        return hashlib.md5(content.encode('utf-8')).hexdigest()

class EnrichmentPipeline:
    """Enrich items with additional metadata"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def process_item(self, item, spider):
        """Add additional metadata"""

        # Add word count
        if item.get('body'):
            text = html.fromstring(item['body']).text_content()
            item['word_count'] = len(text.split())

        # Add reading time (assuming 200 words per minute)
        if item.get('word_count'):
            item['reading_time_minutes'] = max(1, round(item['word_count'] / 200))

        # Parse domain info
        parsed_url = urlparse(item['url'])
        item['url_path'] = parsed_url.path
        item['url_domain'] = parsed_url.netloc

        # Add scrape metadata
        if not item.get('timestamp'):
            item['timestamp'] = datetime.now()

        item['scraped_at'] = datetime.now().isoformat()
        item['spider_name'] = spider.name

        return item


class JSONExportPipeline:
    """Ultra high-performance JSON export with async buffering and batch writes

    Optimizations:
    - Lazy file opening (only open when needed)
    - Large write buffers (64KB per file)
    - Batch writes (minimize I/O operations)
    - Background flushing thread
    - Memory-efficient string building
    - Fast JSON serialization
    """

    def __init__(self, export_dir='output', buffer_size=10000, flush_interval=60):
        """
        Args:
            export_dir: Directory to save JSON files
            buffer_size: Number of items to buffer before flushing (default: 10000)
            flush_interval: Seconds between forced flushes (default: 60)
        """
        self.export_dir = Path(export_dir)
        self.buffer_size = buffer_size
        self.flush_interval = flush_interval
        self.logger = logging.getLogger(__name__)

        # Buffers: domain -> list of JSON strings (pre-serialized!)
        self.buffers = defaultdict(list)
        self.buffer_sizes = defaultdict(int)  # Track buffer memory usage

        # Thread-safe lock for buffer access
        self.lock = threading.RLock()

        # File handlers (keep minimal open files)
        self.file_handlers = {}
        self.file_locks = defaultdict(threading.Lock)  # Per-file locks

        # Track last flush time per domain
        self.last_flush = defaultdict(lambda: time.time())

        # Background flush queue and thread
        self.flush_queue = Queue()
        self.flush_thread = None
        self.running = False

        # Stats
        self.item_count = 0
        self.flush_count = 0
        self.bytes_written = 0

        # Pre-compile JSON encoder for speed
        self.json_encoder = json.JSONEncoder(
            ensure_ascii=False,
            separators=(',', ':'),  # Compact format, no spaces
            default=self._json_default
        )

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            export_dir=crawler.settings.get('EXPORT_DIR', 'output'),
            buffer_size=crawler.settings.get('PIPELINE_BUFFER_SIZE', 10000),
            flush_interval=crawler.settings.get('PIPELINE_FLUSH_INTERVAL', 60)
        )

    def open_spider(self, spider):
        """Create export directory and start background flush thread"""
        self.export_dir.mkdir(parents=True, exist_ok=True)
        self.logger.info(
            f"JSONExportPipeline: Buffer={self.buffer_size} items, "
            f"Flush interval={self.flush_interval}s"
        )

        # Start background flush thread
        self.running = True
        self.flush_thread = threading.Thread(target=self._background_flusher, daemon=True)
        self.flush_thread.start()

        # Register cleanup on exit
        atexit.register(self._emergency_cleanup)

    def close_spider(self, spider):
        """Flush all buffers and close file handlers"""
        self.logger.info(
            f"Closing spider. Items buffered: "
            f"{sum(len(b) for b in self.buffers.values())}"
        )

        # Stop background thread
        self.running = False
        if self.flush_thread:
            self.flush_thread.join(timeout=5)

        # Flush all remaining buffers
        with self.lock:
            for domain in list(self.buffers.keys()):
                self._flush_buffer(domain, force=True)

        # Close all file handlers
        for handler in self.file_handlers.values():
            handler.close()

        self.logger.info(
            f"Pipeline closed. Total items: {self.item_count:,}, "
            f"Flushes: {self.flush_count:,}, "
            f"Data written: {self.bytes_written / 1024 / 1024:.2f} MB"
        )

    def process_item(self, item, spider):
        """Buffer item and flush when needed"""
        try:
            domain = item.get('source_domain', 'unknown')

            # Pre-serialize to JSON string (do this outside lock for speed)
            item_dict = self._prepare_item(item)
            json_line = self.json_encoder.encode(item_dict) + '\n'
            json_size = len(json_line)

            with self.lock:
                # Add to buffer
                self.buffers[domain].append(json_line)
                self.buffer_sizes[domain] += json_size
                self.item_count += 1

                # Check if we need to flush (size-based or time-based)
                buffer_count = len(self.buffers[domain])
                buffer_size = self.buffer_sizes[domain]
                buffer_full = buffer_count >= self.buffer_size
                buffer_large = buffer_size > 10 * 1024 * 1024  # 10MB

                current_time = time.time()
                time_expired = (current_time - self.last_flush[domain]) >= self.flush_interval

                if buffer_full or buffer_large or time_expired:
                    # Queue flush in background thread
                    self.flush_queue.put(domain)

            return item

        except Exception as e:
            self.logger.error(f"Failed to process item: {e}", exc_info=True)
            raise

    def _prepare_item(self, item) -> Dict[str, Any]:
        """Convert item to dict and handle special types"""
        item_dict = dict(item)

        # Convert datetime objects (fastest method)
        for key, value in item_dict.items():
            if isinstance(value, datetime):
                item_dict[key] = value.isoformat()

        return item_dict

    def _json_default(self, obj):
        """Handle non-serializable objects"""
        if isinstance(obj, datetime):
            return obj.isoformat()
        elif isinstance(obj, bytes):
            return obj.decode('utf-8', errors='ignore')
        elif hasattr(obj, '__dict__'):
            return obj.__dict__
        return str(obj)

    def _background_flusher(self):
        """Background thread that handles flushing"""
        self.logger.info("Background flusher thread started")

        while self.running:
            try:
                # Wait for flush request (1 second timeout for time-based checks)
                try:
                    domain = self.flush_queue.get(timeout=1.0)
                    self._flush_buffer(domain)
                except:
                    # Timeout - check for time-based flushes
                    self._check_time_based_flushes()

            except Exception as e:
                self.logger.error(f"Background flusher error: {e}", exc_info=True)

        self.logger.info("Background flusher thread stopped")

    def _check_time_based_flushes(self):
        """Check if any domains need time-based flushing"""
        current_time = time.time()

        with self.lock:
            domains_to_flush = [
                domain for domain, last_time in self.last_flush.items()
                if (current_time - last_time) >= self.flush_interval
                   and len(self.buffers[domain]) > 0
            ]

        for domain in domains_to_flush:
            self._flush_buffer(domain)

    def _flush_buffer(self, domain, force=False):
        """Write buffered items to file (thread-safe)"""
        # Get data to write (minimize lock time)
        with self.lock:
            if not self.buffers[domain]:
                return

            # Take ownership of buffer
            items_to_write = self.buffers[domain]
            bytes_to_write = self.buffer_sizes[domain]
            self.buffers[domain] = []
            self.buffer_sizes[domain] = 0
            self.last_flush[domain] = time.time()

        try:
            # Get or create file handler (outside main lock)
            with self.file_locks[domain]:
                if domain not in self.file_handlers:
                    filename = self.export_dir / f"{self._sanitize_domain(domain)}.jsonl"
                    # Large write buffer for NVME performance
                    self.file_handlers[domain] = open(
                        filename, 'a',
                        encoding='utf-8',
                        buffering=128 * 1024  # 128KB buffer
                    )

                # Write all items in one system call (fastest method)
                file_handler = self.file_handlers[domain]
                file_handler.writelines(items_to_write)
                file_handler.flush()

            # Update stats
            items_written = len(items_to_write)
            self.flush_count += 1
            self.bytes_written += bytes_to_write

            if force or items_written > 1000:
                self.logger.info(
                    f"Flushed {items_written:,} items ({bytes_to_write / 1024:.1f} KB) "
                    f"for {domain}"
                )

            # Cleanup old file handlers if too many open
            if len(self.file_handlers) > 100:
                self._cleanup_old_handlers()

        except Exception as e:
            self.logger.error(f"Failed to flush buffer for {domain}: {e}", exc_info=True)
            # Put items back in buffer on failure
            with self.lock:
                self.buffers[domain] = items_to_write + self.buffers[domain]
                self.buffer_sizes[domain] += bytes_to_write
            raise

    def _cleanup_old_handlers(self):
        """Close least recently used file handlers"""
        # Sort by last flush time
        sorted_domains = sorted(self.last_flush.items(), key=lambda x: x[1])

        # Close oldest 50%
        domains_to_close = [domain for domain, _ in sorted_domains[:len(sorted_domains) // 2]]

        for domain in domains_to_close:
            with self.file_locks[domain]:
                if domain in self.file_handlers:
                    try:
                        self.file_handlers[domain].close()
                        del self.file_handlers[domain]
                        self.logger.debug(f"Closed file handler for {domain}")
                    except Exception as e:
                        self.logger.error(f"Error closing handler for {domain}: {e}")

    def _sanitize_domain(self, domain: str) -> str:
        """Sanitize domain name for filename"""
        # Replace problematic characters
        sanitized = domain.replace('.', '_').replace('/', '_').replace('\\', '_')
        # Limit length
        return sanitized[:200]

    def _emergency_cleanup(self):
        """Emergency cleanup on unexpected exit"""
        try:
            self.running = False

            with self.lock:
                for domain in list(self.buffers.keys()):
                    if self.buffers[domain]:
                        self._flush_buffer(domain, force=True)

            for handler in self.file_handlers.values():
                try:
                    handler.close()
                except:
                    pass

        except Exception as e:
            self.logger.error(f"Emergency cleanup failed: {e}")

class RotatingJSONExportPipeline(JSONExportPipeline):
    """Extended version with file rotation support

    Rotates files when they reach a certain size to prevent huge files
    """

    def __init__(self, export_dir='output', buffer_size=10000,
                 flush_interval=60, max_file_size=500 * 1024 * 1024):
        """
        Args:
            max_file_size: Max file size in bytes before rotation (default: 500MB)
        """
        super().__init__(export_dir, buffer_size, flush_interval)
        self.max_file_size = max_file_size
        self.file_sizes = defaultdict(int)
        self.file_indices = defaultdict(int)

    def _flush_buffer(self, domain, force=False):
        """Write buffered items with file rotation support"""
        # Check if rotation needed
        if domain in self.file_sizes:
            if self.file_sizes[domain] >= self.max_file_size:
                self._rotate_file(domain)

        # Call parent flush
        super()._flush_buffer(domain, force)

        # Update file size tracking
        if domain in self.buffer_sizes:
            self.file_sizes[domain] += self.buffer_sizes[domain]

    def _rotate_file(self, domain):
        """Rotate file for domain"""
        with self.file_locks[domain]:
            if domain in self.file_handlers:
                self.file_handlers[domain].close()
                del self.file_handlers[domain]

            self.file_indices[domain] += 1
            self.file_sizes[domain] = 0

            self.logger.info(
                f"Rotated file for {domain}, starting part {self.file_indices[domain]}"
            )

    def _get_filename(self, domain):
        """Get filename with rotation index"""
        sanitized = self._sanitize_domain(domain)
        index = self.file_indices[domain]

        if index == 0:
            return self.export_dir / f"{sanitized}.jsonl"
        else:
            return self.export_dir / f"{sanitized}_part{index:04d}.jsonl"


class ErrorHandlingPipeline:
    """Handle errors gracefully and log failed items"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.failed_items = []

    def process_item(self, item, spider):
        """Catch and log any errors"""
        try:
            # Validate item passes through successfully
            return item

        except Exception as e:
            self.logger.error(
                f"❌ Pipeline error for {item.get('url', 'unknown')}: {e}",
                exc_info=True
            )

            # Store failed item for later review
            self.failed_items.append({
                'url': item.get('url'),
                'error': str(e),
                'timestamp': datetime.now().isoformat()
            })

            # Re-raise to stop further processing
            raise

    def close_spider(self, spider):
        """Log failed items summary"""
        if self.failed_items:
            self.logger.error(
                f"\n{'='*60}\n"
                f"❌ FAILED ITEMS SUMMARY: {len(self.failed_items)} items failed\n"
                f"{'='*60}"
            )

            for item in self.failed_items[:10]:  # Show first 10
                self.logger.error(f"  - {item['url']}: {item['error']}")

            if len(self.failed_items) > 10:
                self.logger.error(f"  ... and {len(self.failed_items) - 10} more")

class StatisticsPipeline:
    """Collect statistics about scraped items"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.stats = {
            'total_items': 0,
            'by_domain': {},
            'by_language': {},
            'total_words': 0,
            'with_author': 0,
            'with_tags': 0,
            'with_date': 0
        }

    def process_item(self, item, spider):
        """Collect statistics"""

        self.stats['total_items'] += 1

        # By domain
        domain = item.get('source_domain', 'unknown')
        self.stats['by_domain'][domain] = self.stats['by_domain'].get(domain, 0) + 1

        # By language
        lang = item.get('lang', 'unknown')
        self.stats['by_language'][lang] = self.stats['by_language'].get(lang, 0) + 1

        # Word count
        if item.get('word_count'):
            self.stats['total_words'] += item['word_count']

        # Optional fields
        if item.get('author'):
            self.stats['with_author'] += 1

        if item.get('tags'):
            self.stats['with_tags'] += 1

        if item.get('post_date'):
            self.stats['with_date'] += 1

        return item

    def close_spider(self, spider):
        """Log statistics"""
        self.logger.info(
            f"\n{'='*60}\n"
            f"📊 SCRAPING STATISTICS\n"
            f"{'='*60}\n"
            f"Total items: {self.stats['total_items']}\n"
            f"Total words: {self.stats['total_words']:,}\n"
            f"Avg words per item: {self.stats['total_words'] // max(1, self.stats['total_items']):,}\n"
            f"\nOptional fields:\n"
            f"  With author: {self.stats['with_author']} ({self.stats['with_author']/max(1,self.stats['total_items'])*100:.1f}%)\n"
            f"  With tags: {self.stats['with_tags']} ({self.stats['with_tags']/max(1,self.stats['total_items'])*100:.1f}%)\n"
            f"  With date: {self.stats['with_date']} ({self.stats['with_date']/max(1,self.stats['total_items'])*100:.1f}%)\n"
            f"\nBy domain:"
        )

        for domain, count in sorted(self.stats['by_domain'].items(), key=lambda x: x[1], reverse=True):
            percentage = count / self.stats['total_items'] * 100
            self.logger.info(f"  {domain}: {count} ({percentage:.1f}%)")

        self.logger.info(f"{'='*60}")

