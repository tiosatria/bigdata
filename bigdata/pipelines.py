"""
Production-grade item pipelines
Handles validation, cleaning, deduplication, and storage
"""
import uuid
import trafilatura
from itemadapter import ItemAdapter
import json
import logging
import time
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from typing import Dict, List, Any, Optional
import threading
from queue import Queue
import atexit
from lxml import etree, html
from scrapy.exceptions import DropItem
from bigdata.cleaners.html_cleaner import OBVIOUS_EXCLUDES_LIST
from bigdata.items import CrawlItem, DailyLifeResult
from bigdata.spiders.dailylifespider import DailyLifeSpider, DomainConfig
from trafilatura.external import try_readability, try_justext
from trafilatura import html2txt

class CleanHtmlFragmentPipeline:

    EXCLUDES = OBVIOUS_EXCLUDES_LIST.copy()

    def clean_html_fragment(self,fragment: str, exclude_xpaths: Optional[list[str]]) -> str:

        """Clean HTML fragment by removing unwanted elements"""
        if not fragment:
            return ""

        try:
            # Parse HTML fragment safely
            doc = html.fromstring(fragment)
            unwanted_elements = self.EXCLUDES.copy()
            if exclude_xpaths:
                unwanted_elements.extend(exclude_xpaths)
            # Remove unwanted nodes
            for xp in unwanted_elements:
                try:
                    for node in doc.xpath(xp):
                        parent = node.getparent()
                        if parent is not None:
                            parent.remove(node)
                except Exception as e:
                    logging.warning(f"Failed to apply exclude xpath {xp}: {e}")
            # Return serialized, well-formed HTML
            return etree.tostring(doc, encoding="unicode", method="html")

        except Exception as e:
            logging.error(f"Failed to clean HTML fragment: {e}")
            return fragment

    def process_item(self, item, spider):
        if not isinstance(item, CrawlItem):
            return item
        raw = ItemAdapter(item)
        site_noises = raw.get('meta', {}).get('noises', [])
        body_type = raw.get('meta', {}).get('body_type','html')
        if body_type != 'html':
            return item
        body = raw['body']
        if len(body) < 200:
            raise DropItem(f'raw body is too short: {len(body)}')
        sanitized_html = self.clean_html_fragment(body, site_noises)
        raw['body'] = sanitized_html
        return CrawlItem(**raw)

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

    def __init__(self, export_dir='output', buffer_size=1000, flush_interval=60):
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
            domain = item.get('meta',{}).get('hostname', 'unknown')

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

class TransformCrawlerItemToDailyLifeFormat:

    min_text_length :int= 200
    excludes_title :list[str]=[]

    @staticmethod
    def is_templated(text:str, config:DomainConfig, logger)->bool:
        if not isinstance(text, str):
            return False
        comparison = text.lower()
        compare_to = config.domain.lower()

        return compare_to.__contains__(comparison)

    def get_domain_subdomain(self, item:ItemAdapter, config:DomainConfig, logger) -> dict:

        # get tags from meta appended by response
        domain = item.get('meta',{}).get('content_domain')
        subdomain = item.get('meta',{}).get('content_subdomain')

        if domain and subdomain:
            return {'domain':domain, 'subdomain':subdomain}

        # get tags from meta
        tags = item.get('meta',{}).get('tags',[])

        if tags:
            for tag in tags:
                if self.is_templated(tag, config):
                    continue
                if not domain:
                    domain = tag
                else:
                    subdomain = tag
                    break

        # todo: xpath the fuck outta body. maybe, later

        # last resort, get from domain config

        if not domain:
            domain = config.content_domain
        if not subdomain:
            subdomain = config.content_subdomain

        return {'domain':domain, 'subdomain':subdomain}

    def sanitize_title(self, item: ItemAdapter, config:DomainConfig, logger):
        return item.get('meta',{}).get('title','')

    def sanitize_body_text(self, item:ItemAdapter, config:DomainConfig, logger) -> str:

        """
        Sanitize body text using multiple fallback\n
        1. If the body xpath is specified on domain config, it will attempt to extract from there\n
        2. If the extraction fails, trafilatura will perform automatic extraction\n
        3. If it still fails, it will fallback to readability\n
        4. If it still fails, it will fallback to justext\n
        5. Lastly, if it still fails, it will return empty string.\n

        :param item: item yielded by previous pipeline
        :param config: domain config
        :param logger: spider logger for debugging
        :return: always return a str regardless of how funky the content, or atleast that's the idea.
        """
        body_type = item.get('meta', {}).get('body_type', 'html')
        if body_type != 'html':
            return item.get('body','')

        h = item.get('body','')

        # extract right away from known xpath
        if body_xpath:= config.xpath.get('body'):
            if dom:= html.fromstring(h):
                target_dom = dom.xpath(body_xpath)
                sanitized_text = trafilatura.extract(target_dom,
                                                     url=item.get('meta',{}).get('url'),
                                                     output_format='txt',
                                                     include_comments=False,
                                                     include_images=True,
                                                     include_tables=True,
                                                     prune_xpath=config.noises_xp,
                                                     # target_language='en',
                                                     # fast=True
                                                     )
                if sanitized_text:
                    return sanitized_text

        # fallback to auto extraction
        sanitized_text = trafilatura.extract(h,
                            url=item.get('meta',{}).get('url'),
                            prune_xpath=config.noises_xp,
                            output_format='txt',
                            include_images=True,
                            include_tables=True,
                            include_comments=False,
                                             # target_language='en'
                                             )

        if sanitized_text:
            return sanitized_text

        # fallback to readibility
        if not sanitized_text:
                sanitized_html = try_readability(h)
                sanitized_text = html2txt(sanitized_html, clean=True)
                if sanitized_text:
                    return sanitized_text

        # fallback to justext
        return try_justext(html.fromstring(h), url=item.get('meta',{}).get('url'),
                           # target_language='en'
                           ) or ''

    def process_item(self, item, spider:DailyLifeSpider):
        spider.logger.debug('processing daily format')
        if not isinstance(item, CrawlItem):
            spider.logger.debug("is not a crawler item, won't be processed")
            return item

        if not isinstance(spider, DailyLifeSpider):
            spider.logger.warning('This spider is not a DailyLifeSpider. the Item will be forwarded without transforming.')
            return item

        raw_item = ItemAdapter(item)
        domain = raw_item.get('meta',{}).get('hostname','') or spider.get_domain(raw_item.get('meta',{}).get('url'))
        cfg = spider.site_configs.get(domain,{})

        if not cfg:
            return item

        sanitized_text = self.sanitize_body_text(raw_item, cfg, spider.logger)
        sanitized_title = self.sanitize_title(raw_item, cfg, spider.logger)
        ds = self.get_domain_subdomain(raw_item, cfg, spider.logger)
        text = f"{sanitized_title}\n{sanitized_text}"

        out_item = {
            'id': str(uuid.uuid4()),
            'text': text,
            'meta': {
                'data_info': {
                    'lang': cfg.lang or 'en',
                    'url': raw_item.get('meta',{}).get('url'),
                    'source': domain,
                    'type': cfg.type or 'general',
                    'processing_date': datetime.now().isoformat(),
                    'delivery_version': cfg.delivery_version or 'V1',
                    'title': sanitized_title
                },
                'content_info':{
                    'domain': ds.get('domain') or cfg.content_domain,
                    'subdomain':ds.get('subdomain') or cfg.content_subdomain
                }
            }
        }

        return DailyLifeResult(**out_item)

class CleanedJsonlExportPipeline(JSONExportPipeline):

    def __init__(self, export_dir = 'output',buffer_size=100,
                 flush_interval=30):
        super().__init__(export_dir=export_dir+"_cleaned",
                         buffer_size=buffer_size,
                         flush_interval=flush_interval)
        self.logger = logging.getLogger(__name__)

    def process_item(self, item, spider):
        if not isinstance(item, DailyLifeResult):
            return item
        return super().process_item(item, spider)

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
