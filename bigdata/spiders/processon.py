import scrapy
from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from pathlib import Path
import hashlib
import os
from scrapy_playwright.page import PageMethod
import asyncio
import sys



class ProcessOnSpider(CrawlSpider):
    name = 'processon'
    allowed_domains = ['processon.com']

    start_urls = ['https://www.processon.com/template/search/%E7%A8%8B%E5%BA%8F%E6%B5%81%E7%A8%8B%E5%9B%BE_free']

    rules = [
        Rule(LxmlLinkExtractor(restrict_xpaths="//a[@class='item-title-a']"), callback='parse_item',
             process_request='apply_request_meta_item'),
        Rule(LxmlLinkExtractor(restrict_xpaths="//div[@class='page-item-left pageItem']"), follow=True,
             process_request='apply_request_meta'),
    ]

    custom_settings = {
        'CONCURRENT_REQUESTS': 4,  # Reduced for stability
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
        'DOWNLOAD_DELAY': 2,
        'RANDOMIZE_DOWNLOAD_DELAY': True,

        # Playwright settings
        'DOWNLOAD_HANDLERS': {
            'http': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
            'https': 'scrapy_playwright.handler.ScrapyPlaywrightDownloadHandler',
        },
        'TWISTED_REACTOR': 'twisted.internet.asyncioreactor.AsyncioSelectorReactor',

        'PLAYWRIGHT_BROWSER_TYPE': 'chromium',
        'PLAYWRIGHT_LAUNCH_OPTIONS': {
            'headless': True,
        },

        'PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT': 60000,  # Increased timeout
        'DOWNLOAD_TIMEOUT': 90,

        # Output
        'FEEDS': {
            'output/flowcharts_data.jsonl': {
                'format': 'jsonlines',
                'encoding': 'utf8',
                'overwrite': False,
            },
        },

        'RETRY_TIMES': 2,
        'RETRY_HTTP_CODES': [500, 502, 503, 504, 408, 429],
    }

    def __init__(self, *args, **kwargs):
        super(ProcessOnSpider, self).__init__(*args, **kwargs)
        # Create output directory
        Path('./output/flowcharts').mkdir(parents=True, exist_ok=True)
        Path('./output/data').mkdir(parents=True, exist_ok=True)
        self.screenshot_count = 0
        self.failed_count = 0

    def apply_request_meta_item(self, request, response):
        """Apply meta for item pages with Playwright screenshot"""
        req = self.apply_request_meta(request, response)
        req.meta['playwright'] = True
        req.meta['playwright_include_page'] = True
        # DON'T use page_methods - they're causing issues
        # We'll handle waiting in parse_item instead
        return req

    def apply_request_meta(self, request, response):
        if hasattr(self, 'use_proxy') and self.use_proxy:
            request.meta['use_proxy'] = True
        return request

    def sanitize_filename(self, filename):
        """Remove invalid characters from filename"""
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        # Limit length
        return filename[:100]

    def closed(self, reason):
        """Spider closed callback"""
        self.logger.info(f"Spider closed: {reason}")
        self.logger.info(f"Total screenshots captured: {self.screenshot_count}")
        self.logger.info(f"Total failed: {self.failed_count}")

    async def parse_item(self, response):
        """Parse flowchart page and take screenshot"""
        page = None
        try:
            # Get page object from Playwright
            page = response.meta.get('playwright_page')
            if not page:
                self.logger.error(f"No playwright page for {response.url}")
                self.failed_count += 1
                return

            # Extract metadata first
            title = response.xpath("//title/text()").get() or 'untitled'
            title = self.sanitize_filename(title)

            # Generate unique filename
            url_hash = hashlib.md5(response.url.encode()).hexdigest()[:8]
            filename = f"{title}_{url_hash}.png"
            filepath = os.path.join('./output/flowcharts', filename)

            self.logger.info(f"Processing: {response.url}")

            try:
                # FIXED: Use correct selector - just 'iframe' without class
                # Wait for ANY iframe element (don't specify class)
                self.logger.debug("Waiting for iframe...")

                try:
                    # Try multiple selectors
                    iframe_element = None

                    # Try 1: Wait for iframe in .mind_view div
                    try:
                        await page.wait_for_selector('.mind_view iframe', timeout=15000)
                        iframe_element = await page.query_selector('.mind_view iframe')
                        self.logger.debug("Found iframe using .mind_view iframe selector")
                    except:
                        pass

                    # Try 2: Wait for any iframe
                    if not iframe_element:
                        await page.wait_for_selector('iframe', timeout=15000)
                        iframe_element = await page.query_selector('iframe')
                        self.logger.debug("Found iframe using general iframe selector")

                    if not iframe_element:
                        self.logger.error(f"No iframe found for {response.url}")
                        self.failed_count += 1
                        return

                except Exception as e:
                    self.logger.error(f"Timeout waiting for iframe on {response.url}: {e}")
                    self.failed_count += 1
                    return

                # Wait for iframe to load content
                self.logger.debug("Waiting for iframe content to load...")
                await page.wait_for_timeout(4000)  # Increased wait time

                # Get iframe content frame
                iframe = await iframe_element.content_frame()
                if not iframe:
                    self.logger.error(f"Could not access iframe content for {response.url}")
                    self.failed_count += 1
                    return

                self.logger.debug("Accessing iframe content...")

                # Wait for the canvas to appear inside iframe
                try:
                    await iframe.wait_for_selector('#designer_canvas', timeout=20000)
                    self.logger.debug("Canvas found inside iframe")
                except Exception as e:
                    self.logger.error(f"Canvas not found in iframe for {response.url}: {e}")
                    self.failed_count += 1
                    return

                # Additional wait for canvas rendering
                await page.wait_for_timeout(2000)

                # Take screenshot of the iframe (which contains the flowchart)
                await iframe_element.screenshot(path=filepath)
                self.screenshot_count += 1
                self.logger.info(f"✓ Screenshot {self.screenshot_count}: {filename}")

                # Extract canvas dimensions from iframe
                try:
                    canvas_info = await iframe.evaluate('''() => {
                        const canvas = document.querySelector('#designer_canvas');
                        if (canvas) {
                            const style = window.getComputedStyle(canvas);
                            return {
                                width: style.width,
                                height: style.height,
                                shapeCount: document.querySelectorAll('.shape_box').length
                            };
                        }
                        return null;
                    }''')
                except:
                    canvas_info = None

                # Extract additional data
                yield {
                    'url': response.url,
                    'title': title,
                    'filename': filename,
                    'screenshot_path': filepath,
                    'view_count': response.xpath(
                        "//span[@class='view_count']//span[@class='count left_item_text']/text()").get(),
                    'clone_count': response.xpath(
                        "//span[@class='view_clone_count']//span[@class='count left_item_text']/text()").get(),
                    'like_count': response.xpath("//span[@class='like_count']//span[@class='count']/text()").get(),
                    'fav_count': response.xpath(
                        "//div[@class='fav_count file_head_right_item']//span[@class='count']/text()").get(),
                    'canvas_width': canvas_info.get('width') if canvas_info else None,
                    'canvas_height': canvas_info.get('height') if canvas_info else None,
                    'shape_count': canvas_info.get('shapeCount') if canvas_info else 0,
                }

            except Exception as e:
                self.logger.error(f"Screenshot failed for {response.url}: {str(e)}")
                self.failed_count += 1

        except Exception as e:
            self.logger.error(f"Error parsing {response.url}: {str(e)}")
            self.failed_count += 1
        finally:
            # Close the page to free memory
            if page:
                try:
                    await page.close()
                except Exception as e:
                    self.logger.debug(f"Error closing page: {e}")