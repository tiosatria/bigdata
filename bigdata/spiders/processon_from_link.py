import scrapy
from scrapy.exceptions import CloseSpider
import json
import hashlib
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any
import asyncio
import random
from urllib.parse import urlparse

try:
    from playwright.async_api import async_playwright
    from playwright._impl._errors import TimeoutError as PWTimeoutError
except Exception:
    async_playwright = None
    PWTimeoutError = Exception


def parse_url(url_str: str) -> list[str]:
    if not url_str:
        return []
    return url_str.split(',')


class ProcessonFromLink(scrapy.Spider):
    custom_settings = {
        'CONCURRENT_REQUESTS': 48,
        'DOWNLOAD_DELAY': 0,
        'PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT': 60000,
        'DOWNLOAD_TIMEOUT': 90,
        'ITEM_PIPELINES': {},
        'RETRY_TIMES': 2,
        'SCHEDULER_FLUSH_ON_START': True,
        # Keep only image/media aborted to avoid altering canvas/font rendering
        'PLAYWRIGHT_ABORT_REQUEST': lambda request: request.resource_type in [
            'image', 'media'
        ],
    }

    name = 'processon_from_link'
    allowed_domains = ['processon.com']

    @classmethod
    def from_crawler(cls, crawler, *args, **kwargs):
        session = kwargs.get('session') or 'default'
        session = (session or 'default').strip() or 'default'
        feed_output_path = f"output/flowcharts_raw_data_{session}.jsonl"
        feeds_conf = {
            feed_output_path: {
                'format': 'jsonlines',
                'encoding': 'utf8',
                'overwrite': False,
            }
        }
        try:
            crawler.settings.set('FEEDS', feeds_conf, priority='spider')
        except Exception:
            pass

        spider = super(ProcessonFromLink, cls).from_crawler(crawler, *args, **kwargs)
        spider.feed_output_path = feed_output_path
        return spider

    def parse_jsonl_url(self, path: str) -> list[str]:
        if not path:
            return []
        self.logger.info('Parsing jsonl links %s', path)
        with open(path, 'r', encoding='utf-8') as f:
            urls = []
            c = 0
            for line in f.readlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                j = json.loads(line)
                urls.append(j['url'])
                c += 1
            self.logger.info('Prepared %s urls', c)
            return urls

    def __init__(self, url=None,
                 url_jsonl=None,
                 limit=None,
                 skip: int = 0,
                 session: Optional[str] = None,
                 disable_proxy=False,
                 engine: str = 'playwright',
                 # OPTIMIZATION: Reduced defaults for stability
                 engine_contexts: int = 4,  # How many isolated browser contexts (proxies/cookies)
                 engine_concurrency: int = 20,  # HARD LIMIT on simultaneous tabs (The "Sweet Spot")
                 engine_headless: bool = True,
                 engine_retries: int = 2,
                 save_html=False,
                 *args, **kwargs):
        super(ProcessonFromLink, self).__init__(*args, **kwargs)

        eng = (engine or 'playwright').strip().lower()
        if eng in ('x', 'pw-direct', 'direct', 'pd'):
            self.engine = 'pw-direct'
        else:
            self.engine = 'playwright'
        self.disable_proxy = disable_proxy
        self.engine_contexts: int = int(engine_contexts or 8)
        # This is the most important setting: limits active tabs regardless of input size
        self.engine_concurrency: int = int(engine_concurrency or 48)
        self.engine_headless: bool = bool(engine_headless)
        self.engine_retries: int = max(0, int(engine_retries or 2))
        self.save_html = save_html
        self.session_name: str = (session or 'default').strip() or 'default'
        self.feed_output_path: str = f"output/flowcharts_raw_data_{self.session_name}.jsonl"

        urls: List[str] = []
        if url_jsonl:
            urls = self.parse_jsonl_url(url_jsonl)
        if url:
            urls.append(url)

        # no need to dedup this shit
        deduped: List[str] = urls
        # deduped: List[str] = []
        # seen = set()
        # for u in urls:
        #     if not u or u in seen: continue
        #     seen.add(u)
        #     deduped.append(u)

        self.skip: int = int(skip) if skip else 0
        if self.skip > 0:
            deduped = deduped[self.skip:]
        self.limit_collection: int = int(limit) if limit else 0

        self.url_list: List[str] = deduped
        if not self.url_list:
            raise CloseSpider(reason='No url or url_list is provided.')

        self.collected_count: int = 0
        self.failed_count: int = 0
        self.failures: List[Dict[str, str]] = []
        self.start_time_utc = datetime.now(timezone.utc)

        Path('./output').mkdir(parents=True, exist_ok=True)
        Path('./output/raw_html').mkdir(parents=True, exist_ok=True)

    def sanitize_filename(self, filename):
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename[:100]

    def _record_failure(self, url: str, reason: str):
        self.failed_count += 1
        self.failures.append({'url': url, 'reason': reason})

    def start_requests(self):
        urls = self.url_list
        if self.limit_collection > 0:
            urls = urls[: self.limit_collection]

        self.logger.info(
            "Starting crawl: session=%s, total_urls=%d, concurrency=%d, contexts=%d",
            self.session_name, len(urls), self.engine_concurrency, self.engine_contexts
        )

        if self.engine == 'pw-direct':
            yield scrapy.Request(
                url='https://processon.com',
                callback=self.run_pw_direct_handler,
                dont_filter=True,
                meta={'engine_bootstrap': True}
            )
            return

        # Fallback for standard scrapy-playwright
        for url in urls:
            yield scrapy.Request(url=url, callback=self.parse_item, dont_filter=True)

    async def run_pw_direct_handler(self, response):
        if async_playwright is None:
            self.logger.error("Playwright not installed.")
            return

        urls = self.url_list
        if self.limit_collection > 0:
            urls = urls[: self.limit_collection]

        # Queue for output items
        out_queue: asyncio.Queue = asyncio.Queue(maxsize=500)

        # Start the main runner task
        runner_task = asyncio.create_task(self.run_pw_direct(urls, out_queue))

        # Yield items as they come in from the queue
        try:
            while True:
                item = await out_queue.get()
                if item is None:  # Sentinel for "Done"
                    break
                yield item
        finally:
            try:
                await runner_task
            except Exception as e:
                self.logger.error(f"Runner Error: {e}")

    async def run_pw_direct(self, urls: List[str], out_queue: "asyncio.Queue"):
        pw = await async_playwright().start()

        # Launch args (Standard)
        launch_args = [
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage", "--no-sandbox", "--disable-gpu", "--disable-extensions"
        ]
        browser = await pw.chromium.launch(headless=self.engine_headless, args=launch_args)

        # --- IMPROVEMENT 1: More Contexts, Better Isolation ---
        contexts = []
        # Use more contexts to spread the load (avoid 10 tabs on 1 IP)
        target_contexts = max(self.engine_contexts, int(self.engine_concurrency / 3))

        self.logger.info(f"Initializing {target_contexts} browser contexts for isolation...")

        # (Assuming you have your proxy setup code here as before...)
        sp_settings = getattr(self.crawler, 'settings', {}) or {}
        default_proxy = (sp_settings.get('PLAYWRIGHT_CONTEXTS') or {}).get('default', {}).get('proxy')
        if not default_proxy:
            default_proxy = {'server': 'http://p.webshare.io:80', 'username': 'icpjabta-JP-SG-rotate',
                             'password': 'v3cylfcqz2p5'}

        for i in range(target_contexts):
            try:
                ctx = await browser.new_context(
                    viewport={'width': 1920, 'height': 2000},
                    ignore_https_errors=True,
                    java_script_enabled=True,
                    proxy=None if self.disable_proxy else default_proxy,
                    user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                )
                # Strict blocking to save bandwidth
                await ctx.route("**/*", lambda route: route.abort() if route.request.resource_type in ['image', 'media',
                                                                                                       'font'] else route.continue_())
                contexts.append(ctx)
            except Exception:
                pass

        if not contexts:
            self.logger.error("No contexts created.")
            await out_queue.put(None)
            return

        url_queue: asyncio.Queue = asyncio.Queue()
        for u in urls:
            url_queue.put_nowait(u)

        worker_count = min(len(urls), self.engine_concurrency)
        self.logger.info(f"Starting {worker_count} workers with STAGGERED LAUNCH...")

        workers = []

        async def worker_loop(worker_id):
            # Round-robin assignment
            my_ctx = contexts[worker_id % len(contexts)]

            while True:
                try:
                    url = url_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

                # Retry logic inside the worker
                success = False
                # We retry locally on failure before giving up
                for local_attempt in range(2):
                    try:
                        item = await self.pw_collect(my_ctx, url)
                        if item:
                            await out_queue.put(item)
                            success = True
                            break  # Success, exit retry loop
                    except Exception:
                        # If failed, wait a bit before retry
                        await asyncio.sleep(2)

                if not success:
                    # If we are here, it failed 2 times hard.
                    self.logger.warning(f"Worker {worker_id} gave up on {url}")

                url_queue.task_done()

        # --- IMPROVEMENT 2: Staggered Launch ---
        # DO NOT launch all at once. Launch one every 0.5 seconds.
        for i in range(worker_count):
            workers.append(asyncio.create_task(worker_loop(i)))
            # This prevents the "Thundering Herd" that kills proxies
            await asyncio.sleep(0.5)

        await url_queue.join()
        for w in workers:
            if not w.done(): w.cancel()

        for ctx in contexts:
            await ctx.close()
        await browser.close()
        await pw.stop()
        await out_queue.put(None)

    async def pw_collect(self, ctx, url: str) -> Optional[Dict[str, Any]]:
        page = await ctx.new_page()
        try:
            page.set_default_timeout(60000)

            # 1. Load Page
            await page.goto(url, wait_until='domcontentloaded')

            # Check basic validity
            if "processon.com/view" not in page.url and "processon.com/chart" not in page.url:
                pass  # Handle redirects if necessary

            title = await page.title() or 'untitled'
            title_clean = self.sanitize_filename(title)
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            iframe_el = None
            try:
                await page.wait_for_selector('iframe', state='attached', timeout=20000)
                iframe_el = await page.query_selector('.mind_view iframe') or await page.query_selector('iframe')
            except Exception:
                self._record_failure(url, 'iframe_wait_timeout')
                return None

            if not iframe_el:
                self._record_failure(url, 'iframe_not_found')
                return None

            iframe = await iframe_el.content_frame()
            if not iframe:
                self._record_failure(url, 'iframe_locked')
                return None

            # 3. Wait for CONTENT, not just the container
            # We wait until #designer_canvas exists AND has at least one child element (shapes/lines)
            try:
                await iframe.wait_for_function(
                    "document.querySelector('#designer_canvas') && document.querySelector('#designer_canvas').children.length > 0",
                    timeout=30000
                )
            except Exception:
                # fallback to svg, assuming it's xmind chart
                await iframe.wait_for_function(
                    "document.querySelector('#mind_con') && document.querySelector('#mind_con').children.length > 0",
                    # little timeout cause we already wait before this, so the element should already been attached by now
                    timeout=3000
                )
                svg_str = await iframe.evaluate('''
                ()=>{
                const svg = document.querySelector("svg");
                return svg ? svg.outerHTML : null;
                }
                ''')
                if svg_str:
                    self.log_collect(type='svg')
                    return {
                        'url': url,
                        'url_hash': url_hash,
                        'title': title,
                        'canvas_html': None,
                        'full_html': None,
                        'html_file': None,
                        'svg': svg_str
                    }
                # If it times out here, the chart might be genuinely empty or failed to render
                self._record_failure(url, 'empty_chart_timeout')
                return None

            canvas_data = await iframe.evaluate('''() => {
                const container = document.querySelector('#designer_canvas');
                if (!container) return null;

                // Optional: Quick freeze to ensure we capture canvas visuals if they exist
                container.querySelectorAll('canvas').forEach(canvas => {
                    if (canvas.width > 0 && canvas.height > 0) {
                        try {
                            const img = document.createElement('img');
                            img.src = canvas.toDataURL();
                            img.style.cssText = window.getComputedStyle(canvas).cssText;
                            img.className = canvas.className;
                            canvas.parentNode.replaceChild(img, canvas);
                        } catch(e) {}
                    }
                });

                return {
                    canvasHTML: container.outerHTML,
                    fullHTML: container.parentElement.outerHTML,
                    title: document.title
                };
            }''')

            if not canvas_data:
                self._record_failure(url, 'js_extract_fail')
                return None

            # Save file
            if self.save_html:
                html_filename = f"raw_html/{title_clean}_{url_hash}.html"
                with open(f'output/{html_filename}', 'w', encoding='utf-8') as f:
                    f.write(canvas_data['fullHTML'])

            self.log_collect()

            return {
                'url': url,
                'url_hash': url_hash,
                'title': title,
                'canvas_html': canvas_data['canvasHTML'],
                'full_html': canvas_data['fullHTML'],
                'html_file': html_filename if self.save_html else None,
                'svg': svg
            }

        except Exception as e:
            raise e
        finally:
            await page.close()

    def log_collect(self, type:str='canvas'):
        self.collected_count += 1
        # if self.collected_count % 10 == 0:
        self.logger.info(f"progress: {self.collected_count} collected {type}")

    def parse_item(self, response):
        # Keep existing logic for fallback
        yield from super().parse_item(response)

    def errback_handle(self, failure):
        # Keep existing logic
        pass

    def closed(self, reason):
        finish = datetime.now(timezone.utc)
        elapsed = (finish - self.start_time_utc).total_seconds() if getattr(self, 'start_time_utc', None) else None
        summary = {
            'success_count': self.collected_count,
            'failure_count': self.failed_count,
            'fails': self.failures,
            'elapsed_seconds': elapsed,
        }
        summary_path = f"output/flowcharts_summary_{self.session_name}.json"
        with open(summary_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, ensure_ascii=False, indent=2)
        self.logger.info(f"Spider closed. Collected: {self.collected_count}")