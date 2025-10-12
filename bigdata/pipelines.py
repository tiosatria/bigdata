"""
Production-grade item pipelines
Handles validation, cleaning, deduplication, and storage
"""

from datetime import datetime
from urllib.parse import urlparse
import hashlib
import logging
import re
from pathlib import Path
from itemadapter import ItemAdapter
from lxml import html, etree
from scrapy.exceptions import DropItem

from bigdata.items import ArticleItem


class ValidationPipeline:
    """Validate scraped items before processing"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def process_item(self, item, spider):
        """Validate required fields"""

        # Check required fields
        required_fields = ['url', 'title', 'body', 'source_domain']

        for field in required_fields:
            if not item.get(field):
                self.logger.error(
                    f"❌ Missing required field '{field}' for {item.get('url', 'unknown')}"
                )
                raise DropItem(f"Missing required field: {field}")

        # Validate title length
        if len(item['title']) < 5:
            self.logger.warning(f"Title too short: {item['title']}")
            raise DropItem("Title too short")

        # Validate body length
        if len(item['body']) < 50:
            self.logger.warning(f"Body too short for: {item['url']}")
            raise DropItem("Body content too short")

        return item

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

class DeduplicationPipeline:
    """Remove duplicate items based on content"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.seen_hashes = set()
        self.seen_urls = set()

    def process_item(self, item, spider):
        """Check for duplicates"""

        # Check URL duplication
        if item['url'] in self.seen_urls:
            self.logger.debug(f"Duplicate URL: {item['url']}")
            raise DropItem("Duplicate URL")

        # Check content duplication
        content_hash = item.get('content_hash')
        if content_hash and content_hash in self.seen_hashes:
            self.logger.debug(f"Duplicate content: {item['url']}")
            raise DropItem("Duplicate content")

        # Mark as seen
        self.seen_urls.add(item['url'])
        if content_hash:
            self.seen_hashes.add(content_hash)

        return item

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

class DatabasePipeline:
    """Store items in database (example implementation)"""

    def __init__(self):
        self.logger = logging.getLogger(__name__)
        # Initialize your database connection here
        # self.db = Database()

    def open_spider(self, spider):
        """Initialize database connection"""
        self.logger.info("Opening database connection")
        # self.db.connect()

    def close_spider(self, spider):
        """Close database connection"""
        self.logger.info("Closing database connection")
        # self.db.close()

    def process_item(self, item, spider):
        """Save item to database"""
        try:
            # Example: Save to database
            # self.db.insert('articles', dict(item))

            self.logger.info(f"✓ Saved: {item['title'][:50]}...")

            return item

        except Exception as e:
            self.logger.error(f"Failed to save item: {e}")
            raise

class RedisPipeline:
    """Store items in Redis for further processing"""

    def __init__(self, redis_url):
        self.redis_url = redis_url
        self.logger = logging.getLogger(__name__)
        self.redis_client = None

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            redis_url=crawler.settings.get('REDIS_URL')
        )

    def open_spider(self, spider):
        """Connect to Redis"""
        import redis
        self.redis_client = redis.from_url(self.redis_url)
        self.logger.info("Connected to Redis")

    def close_spider(self, spider):
        """Close Redis connection"""
        if self.redis_client:
            self.redis_client.close()

    def process_item(self, item, spider):
        """Push item to Redis"""
        try:
            import json

            # Convert item to dict
            item_dict = dict(item)

            # Convert datetime objects to strings
            for key, value in item_dict.items():
                if isinstance(value, datetime):
                    item_dict[key] = value.isoformat()

            # Push to Redis list
            key = f"{spider.name}:items"
            self.redis_client.rpush(key, json.dumps(item_dict))

            self.logger.debug(f"Pushed to Redis: {item['url']}")

            return item

        except Exception as e:
            self.logger.error(f"Failed to push to Redis: {e}")
            raise

class JSONExportPipeline:
    """Export items to JSON files"""

    def __init__(self, export_dir='output'):
        self.export_dir = export_dir
        self.logger = logging.getLogger(__name__)
        self.file_handlers = {}

    @classmethod
    def from_crawler(cls, crawler):
        return cls(
            export_dir=crawler.settings.get('EXPORT_DIR', 'output')
        )

    def open_spider(self, spider):
        """Create export directory"""
        import os
        os.makedirs(self.export_dir, exist_ok=True)

    def close_spider(self, spider):
        """Close file handlers"""
        for handler in self.file_handlers.values():
            handler.close()

    def process_item(self, item, spider):
        """Write item to JSON file"""
        try:
            import json

            domain = item['source_domain']

            # Create domain-specific file
            if domain not in self.file_handlers:
                filename = Path(self.export_dir) / f"{domain.replace('.', '_')}.jsonl"
                self.file_handlers[domain] = open(filename, 'a', encoding='utf-8')

            # Convert item to dict
            item_dict = dict(item)

            # Convert datetime objects
            for key, value in item_dict.items():
                if isinstance(value, datetime):
                    item_dict[key] = value.isoformat()

            # Write to file
            self.file_handlers[domain].write(json.dumps(item_dict, ensure_ascii=False) + '\n')
            self.file_handlers[domain].flush()

            return item

        except Exception as e:
            self.logger.error(f"Failed to export to JSON: {e}")
            raise


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

