"""
Persistent Scheduler using SQLite for URL deduplication and state management.
Integrates with existing bigdata spider setup.
"""

import sqlite3
import pickle
from pathlib import Path
from scrapy.utils.request import fingerprint as request_fingerprint
from scrapy.http import Request
from scrapy import signals
from scrapy.dupefilters import BaseDupeFilter
import logging


class SQLitePriorityQueue:
    """SQLite-backed priority queue for requests"""

    def __init__(self, db_path, domain):
        self.db_path = db_path
        self.domain = domain
        self.connection = None
        self._setup_database()

    def _setup_database(self):
        """Initialize database tables"""
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS request_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                priority INTEGER NOT NULL,
                request_data BLOB NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(domain, fingerprint)
            )
        """)
        self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_domain_priority 
            ON request_queue(domain, priority DESC, id ASC)
        """)
        self.connection.commit()

    def push(self, request):
        """Add request to queue"""
        fingerprint = request_fingerprint(request).hex()
        priority = -request.priority

        try:
            # Create a copy of the request without unpicklable attributes
            request_copy = request.replace()
            # Remove unpicklable meta keys
            if 'playwright_page' in request_copy.meta:
                request_copy.meta.pop('playwright_page')
            if 'playwright_context_kwargs' in request_copy.meta:
                # Store as dict instead of keeping potential lambda references
                ctx_kwargs = request_copy.meta['playwright_context_kwargs']
                if callable(ctx_kwargs):
                    request_copy.meta.pop('playwright_context_kwargs')

            self.connection.execute("""
                INSERT OR REPLACE INTO request_queue 
                (domain, fingerprint, priority, request_data)
                VALUES (?, ?, ?, ?)
            """, (self.domain, fingerprint, priority, pickle.dumps(request_copy)))
            self.connection.commit()
        except (sqlite3.IntegrityError, pickle.PicklingError) as e:
            if isinstance(e, pickle.PicklingError):
                # If still can't pickle, store essential info only
                import logging
                logging.getLogger(__name__).warning(f"Could not pickle request {request.url}, storing URL only")
                # Store a new minimal request
                minimal_request = request.replace(callback=None, errback=None)
                minimal_request.meta.clear()
                minimal_request.meta['url'] = request.url
                minimal_request.meta['original_meta_keys'] = list(request.meta.keys())
                try:
                    self.connection.execute("""
                        INSERT OR REPLACE INTO request_queue 
                        (domain, fingerprint, priority, request_data)
                        VALUES (?, ?, ?, ?)
                    """, (self.domain, fingerprint, priority, pickle.dumps(minimal_request)))
                    self.connection.commit()
                except:
                    pass  # Skip if still can't pickle

    def pop(self):
        """Get highest priority request"""
        cursor = self.connection.execute("""
            SELECT id, request_data FROM request_queue
            WHERE domain = ?
            ORDER BY priority DESC, id ASC
            LIMIT 1
        """, (self.domain,))

        row = cursor.fetchone()
        if row:
            req_id, request_data = row
            try:
                request = pickle.loads(request_data)
                self.connection.execute("DELETE FROM request_queue WHERE id = ?", (req_id,))
                self.connection.commit()
                return request
            except Exception as e:
                # If unpickling fails, remove from queue and try next
                import logging
                logging.getLogger(__name__).warning(f"Could not unpickle request (id={req_id}): {e}")
                self.connection.execute("DELETE FROM request_queue WHERE id = ?", (req_id,))
                self.connection.commit()
                return self.pop()  # Try next request
        return None

    def __len__(self):
        """Get queue size"""
        cursor = self.connection.execute(
            "SELECT COUNT(*) FROM request_queue WHERE domain = ?",
            (self.domain,)
        )
        return cursor.fetchone()[0]

    def clear(self):
        """Clear all requests for this domain"""
        self.connection.execute("DELETE FROM request_queue WHERE domain = ?", (self.domain,))
        self.connection.commit()

    def close(self):
        """Close database connection"""
        if self.connection:
            self.connection.close()


class SQLiteDupeFilter(BaseDupeFilter):
    """SQLite-backed duplicate filter with status tracking"""

    def __init__(self, db_path, domain, debug=False):
        self.db_path = db_path
        self.domain = domain
        self.debug = debug
        self.connection = None
        self.logger = logging.getLogger(__name__)
        self._setup_database()

    def _setup_database(self):
        """Initialize database tables"""
        self.connection = sqlite3.connect(self.db_path, check_same_thread=False)

        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS fingerprints (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                domain TEXT NOT NULL,
                fingerprint TEXT NOT NULL,
                url TEXT NOT NULL,
                status TEXT NOT NULL,
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                retry_count INTEGER DEFAULT 0,
                http_status INTEGER,
                UNIQUE(domain, fingerprint)
            )
        """)

        self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_domain_fingerprint 
            ON fingerprints(domain, fingerprint)
        """)

        self.connection.execute("""
            CREATE INDEX IF NOT EXISTS idx_domain_status 
            ON fingerprints(domain, status)
        """)

        self.connection.commit()

    @classmethod
    def from_crawler(cls, crawler):
        """Create instance from crawler"""
        settings = crawler.settings
        domain = getattr(crawler.spider, 'domain', crawler.spider.name)

        db_dir = Path('crawl_state')
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f'{domain}_state.db'

        debug = settings.getbool('DUPEFILTER_DEBUG', False)
        return cls(db_path, domain, debug)

    def request_seen(self, request):
        """Check if request was seen and mark as pending"""
        fingerprint = request_fingerprint(request).hex()

        cursor = self.connection.execute("""
            SELECT status, retry_count FROM fingerprints 
            WHERE domain = ? AND fingerprint = ?
        """, (self.domain, fingerprint))

        row = cursor.fetchone()

        if row:
            status, retry_count = row

            # Allow retrying failed requests
            if status == 'failed':
                max_retries = request.meta.get('max_retry_failed', 3)
                if retry_count < max_retries:
                    self.logger.info(f"Retrying failed URL (attempt {retry_count + 1}): {request.url}")
                    self._update_status(fingerprint, 'pending', retry_count + 1)
                    return False
                else:
                    if self.debug:
                        self.logger.debug(f"Max retries reached for: {request.url}")
                    return True

            if status == 'success':
                if self.debug:
                    self.logger.debug(f"Filtered duplicate (success): {request.url}")
                return True

            if status == 'pending':
                if self.debug:
                    self.logger.debug(f"Filtered duplicate (pending): {request.url}")
                return True

        # New request - mark as pending
        self._insert_or_update(fingerprint, request.url, 'pending')
        return False

    def _insert_or_update(self, fingerprint, url, status, retry_count=0, http_status=None):
        """Insert or update fingerprint record"""
        try:
            self.connection.execute("""
                INSERT INTO fingerprints (domain, fingerprint, url, status, retry_count, http_status)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(domain, fingerprint) 
                DO UPDATE SET 
                    status = excluded.status,
                    last_seen = CURRENT_TIMESTAMP,
                    retry_count = excluded.retry_count,
                    http_status = excluded.http_status
            """, (self.domain, fingerprint, url, status, retry_count, http_status))
            self.connection.commit()
        except sqlite3.Error as e:
            self.logger.error(f"Database error: {e}")

    def _update_status(self, fingerprint, status, retry_count=None, http_status=None):
        """Update status of existing fingerprint"""
        if retry_count is not None:
            self.connection.execute("""
                UPDATE fingerprints 
                SET status = ?, retry_count = ?, http_status = ?, last_seen = CURRENT_TIMESTAMP
                WHERE domain = ? AND fingerprint = ?
            """, (status, retry_count, http_status, self.domain, fingerprint))
        else:
            self.connection.execute("""
                UPDATE fingerprints 
                SET status = ?, http_status = ?, last_seen = CURRENT_TIMESTAMP
                WHERE domain = ? AND fingerprint = ?
            """, (status, http_status, self.domain, fingerprint))
        self.connection.commit()

    def mark_success(self, request, http_status=200):
        """Mark request as successfully processed"""
        fingerprint = request_fingerprint(request).hex()
        self._update_status(fingerprint, 'success', http_status=http_status)

    def mark_failed(self, request, http_status=None):
        """Mark request as failed"""
        fingerprint = request_fingerprint(request).hex()
        cursor = self.connection.execute("""
            SELECT retry_count FROM fingerprints 
            WHERE domain = ? AND fingerprint = ?
        """, (self.domain, fingerprint))
        row = cursor.fetchone()
        retry_count = row[0] if row else 0
        self._update_status(fingerprint, 'failed', retry_count, http_status)

    def get_stats(self):
        """Get crawl statistics"""
        cursor = self.connection.execute("""
            SELECT status, COUNT(*) as count
            FROM fingerprints
            WHERE domain = ?
            GROUP BY status
        """, (self.domain,))

        stats = dict(cursor.fetchall())
        return {
            'success': stats.get('success', 0),
            'failed': stats.get('failed', 0),
            'pending': stats.get('pending', 0),
            'total': sum(stats.values())
        }

    def get_failed_urls(self, limit=None):
        """Get list of failed URLs"""
        query = """
            SELECT url, retry_count, http_status, last_seen 
            FROM fingerprints
            WHERE domain = ? AND status = 'failed'
            ORDER BY last_seen DESC
        """
        if limit:
            query += f" LIMIT {limit}"

        cursor = self.connection.execute(query, (self.domain,))
        return cursor.fetchall()

    def reset_failed_urls(self):
        """Reset all failed URLs to allow recrawling"""
        cursor = self.connection.execute("""
            SELECT COUNT(*) FROM fingerprints 
            WHERE domain = ? AND status = 'failed'
        """, (self.domain,))
        count = cursor.fetchone()[0]

        self.connection.execute("""
            UPDATE fingerprints 
            SET status = 'pending', retry_count = 0
            WHERE domain = ? AND status = 'failed'
        """, (self.domain,))
        self.connection.commit()

        self.logger.info(f"Reset {count} failed URLs for domain: {self.domain}")
        return count

    def close(self, reason):
        """Close database connection"""
        if self.connection:
            # Get stats before closing
            try:
                stats = self.get_stats()
                self.logger.info(f"Crawl stats for {self.domain}: {stats}")
            except Exception as e:
                self.logger.warning(f"Could not get final stats: {e}")

            # Now close connection
            try:
                self.connection.close()
                self.connection = None
            except Exception as e:
                self.logger.warning(f"Error closing connection: {e}")


class SQLiteScheduler:
    """Custom scheduler using SQLite for persistence"""

    def __init__(self, dupefilter, db_path, domain, persist=True, flush_on_start=False):
        self.df = dupefilter
        self.db_path = db_path
        self.domain = domain
        self.persist = persist
        self.flush_on_start = flush_on_start
        self.spider = None
        self.queue = None
        self.logger = logging.getLogger(__name__)

    @classmethod
    def from_crawler(cls, crawler):
        settings = crawler.settings
        domain = getattr(crawler.spider, 'domain', crawler.spider.name)

        db_dir = Path('crawl_state')
        db_dir.mkdir(parents=True, exist_ok=True)
        db_path = db_dir / f'{domain}_state.db'

        dupefilter = SQLiteDupeFilter.from_crawler(crawler)
        persist = settings.getbool('SCHEDULER_PERSIST', True)
        flush_on_start = settings.getbool('SCHEDULER_FLUSH_ON_START', False)

        scheduler = cls(dupefilter, db_path, domain, persist, flush_on_start)

        # Connect signals
        crawler.signals.connect(scheduler.spider_closed, signal=signals.spider_closed)
        crawler.signals.connect(scheduler.response_received, signal=signals.response_received)
        crawler.signals.connect(scheduler.request_reached_downloader, signal=signals.request_reached_downloader)

        return scheduler

    def open(self, spider):
        """Initialize scheduler"""
        self.spider = spider
        self.queue = SQLitePriorityQueue(self.db_path, self.domain)

        if self.flush_on_start:
            self.logger.info(f"Flushing queue for {self.domain}")
            self.queue.clear()

        queue_size = len(self.queue)
        if queue_size > 0:
            self.logger.info(f"Resuming crawl for {self.domain} with {queue_size} pending requests")

        stats = self.df.get_stats()
        self.logger.info(f"Starting stats - Success: {stats['success']}, Failed: {stats['failed']}, Total: {stats['total']}")

    def close(self, reason):
        """Close scheduler"""
        if self.queue:
            queue_size = len(self.queue)
            if queue_size > 0:
                self.logger.info(f"Closing scheduler with {queue_size} pending requests (will resume next time)")
            self.queue.close()
        self.df.close(reason)

    def enqueue_request(self, request:Request):
        """Add request to queue"""

        if not self.df.request_seen(request):
            self.queue.push(request)
            self.logger.debug(f"Enqueued: {request.url}")
            return True
        else:
            self.logger.debug(f"Request filtered: {request.url}")
            return False

    def next_request(self):
        """Get next request from queue"""
        return self.queue.pop()

    def has_pending_requests(self):
        """Check if there are pending requests"""
        pending = len(self.queue) > 0
        if not pending:
            self.logger.debug(f"No pending requests in queue (size: {len(self.queue)})")
        return pending

    def spider_closed(self, spider):
        """Handle spider closed signal"""
        try:
            if hasattr(self.df, 'connection') and self.df.connection:
                stats = self.df.get_stats()
                self.logger.info("=" * 80)
                self.logger.info(f"Spider closed - Final stats:")
                self.logger.info(f"  Success: {stats['success']}")
                self.logger.info(f"  Failed: {stats['failed']}")
                self.logger.info(f"  Pending: {stats['pending']}")
                self.logger.info(f"  Total: {stats['total']}")

                failed_urls = self.df.get_failed_urls(limit=10)
                if failed_urls:
                    self.logger.info(f"\nTop 10 failed URLs:")
                    for url, retry_count, http_status, last_seen in failed_urls:
                        self.logger.info(f"  {url} (HTTP {http_status}, retries: {retry_count})")
                self.logger.info("=" * 80)
        except Exception as e:
            self.logger.warning(f"Error getting final stats: {e}")

    def response_received(self, response, request, spider):
        """Handle successful response"""
        if response.status < 400:
            self.df.mark_success(request, response.status)
        else:
            self.df.mark_failed(request, response.status)

    def request_reached_downloader(self, request, spider):
        """Track when request is being processed"""
        pass