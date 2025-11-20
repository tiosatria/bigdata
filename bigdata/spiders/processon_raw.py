"""
Phase 1: Data Collection Spider
Collects iframe HTML and metadata WITHOUT rendering images
Much faster - can scrape 50K pages in 1-2 days instead of 10 days
"""

from scrapy.linkextractors.lxmlhtml import LxmlLinkExtractor
from scrapy.spiders import CrawlSpider, Rule
from pathlib import Path
import hashlib

class ProcessOnRawDataSpider(CrawlSpider):
    """
    Collects flowchart data without rendering
    MUCH faster than screenshot approach
    """

    name = 'processon_data'
    allowed_domains = ['processon.com']

    start_urls = ['https://www.processon.com/template/search/%E7%A8%8B%E5%BA%8F%E6%B5%81%E7%A8%8B%E5%9B%BE_free']

    rules = [
        Rule(
            LxmlLinkExtractor(restrict_xpaths="//a[@class='item-title-a']"),
            callback='parse_item',
            process_request='apply_request_meta_item'
        ),
        Rule(
            LxmlLinkExtractor(restrict_xpaths="//div[@id='tempPagination']"),
            follow=True,
            process_request='apply_request_meta'
        ),
    ]

    custom_settings = {
        'CONCURRENT_REQUESTS': 100,  # Can be higher since no rendering
        'CONCURRENT_REQUESTS_PER_DOMAIN': 4,
        # 'DOWNLOAD_DELAY': 0.5,
        'PLAYWRIGHT_DEFAULT_NAVIGATION_TIMEOUT': 45000,
        'DOWNLOAD_TIMEOUT': 60,
        # Output to JSONL for easy batch processing
        'FEEDS': {
            'output/flowcharts_raw_data.jsonl': {
                'format': 'jsonlines',
                'encoding': 'utf8',
                'overwrite': False,
            },
        },
        'ITEM_PIPELINES': {},
        'RETRY_TIMES': 5,
    }

    def __init__(self, *args, **kwargs):
        super(ProcessOnRawDataSpider, self).__init__(*args, **kwargs)
        Path('./output/raw_html').mkdir(parents=True, exist_ok=True)
        self.collected_count = 0
        self.failed_count = 0

    def apply_request_meta_item(self, request, response):
        req = self.apply_request_meta(request, response)
        req.meta['playwright'] = True
        req.meta['playwright_include_page'] = True
        return req

    def apply_request_meta(self, request, response):
        request.meta['use_proxy'] = True
        return request

    def sanitize_filename(self, filename):
        invalid_chars = '<>:"/\\|?*'
        for char in invalid_chars:
            filename = filename.replace(char, '_')
        return filename[:100]

    async def parse_item(self, response):
        """
        Extract iframe HTML and metadata
        NO screenshot rendering - super fast!
        """
        page = None
        try:
            page = response.meta.get('playwright_page')
            if not page:
                self.logger.error(f"No playwright page for {response.url}")
                self.failed_count += 1
                return

            title = response.xpath("//title/text()").get() or 'untitled'
            title_clean = self.sanitize_filename(title)

            url_hash = hashlib.md5(response.url.encode()).hexdigest()[:8]

            self.logger.info(f"Collecting: {response.url}")

            try:
                # Wait for iframe
                try:
                    await page.wait_for_selector('.mind_view iframe', timeout=45000)
                    iframe_element = await page.query_selector('.mind_view iframe')
                except:
                    await page.wait_for_selector('iframe', timeout=45000)
                    iframe_element = await page.query_selector('iframe')

                if not iframe_element:
                    self.logger.error(f"No iframe for {response.url}")
                    self.failed_count += 1
                    return

                # Wait for iframe content
                await page.wait_for_timeout(3000)

                iframe = await iframe_element.content_frame()
                if not iframe:
                    self.logger.error(f"Cannot access iframe content for {response.url}")
                    self.failed_count += 1
                    return

                # Wait for canvas
                await iframe.wait_for_selector('#designer_canvas', timeout=30000)
                await page.wait_for_timeout(1000)

                # Extract ALL the data we need for later rendering
                canvas_data = await iframe.evaluate('''() => {
                                    const container = document.querySelector('#designer_canvas');
                                    if (!container) return null;

                                    // Helper function to convert canvas to image
                                    const freezeCanvas = (canvas) => {
                                        if (!canvas || !canvas.width || !canvas.height) return;

                                        try {
                                            // 1. Get Data URL
                                            const dataUrl = canvas.toDataURL('image/png');

                                            // 2. Create replacement Image
                                            const img = document.createElement('img');
                                            img.src = dataUrl;

                                            // 3. Copy critical computed styles
                                            const style = window.getComputedStyle(canvas);
                                            img.style.width = '100%';   // Force fill parent
                                            img.style.height = '100%';  // Force fill parent
                                            img.className = canvas.className;

                                            // 4. Replace
                                            canvas.parentNode.replaceChild(img, canvas);
                                        } catch(e) {
                                            console.error("Canvas freeze error:", e);
                                        }
                                    };

                                    // 1. Convert SHAPE canvases
                                    container.querySelectorAll('.shape_box:not(.linker_box) canvas').forEach(freezeCanvas);

                                    // 2. Convert ARROW (Linker) canvases - These are critical!
                                    container.querySelectorAll('.linker_box canvas').forEach(freezeCanvas);

                                    // 3. Return data
                                    return {
                                        canvasHTML: container.outerHTML,
                                        canvasStyle: container.getAttribute('style'),
                                        shapes: [], // We don't strictly need this array if we have the full HTML
                                        width: container.style.width || '1050px',
                                        height: container.style.height || '1500px',
                                        fullHTML: container.parentElement.outerHTML,
                                        cssLinks: [],
                                        inlineStyles: Array.from(document.querySelectorAll('style')).map(s => s.textContent),
                                    };
                                }''')

                if not canvas_data:
                    self.logger.error(f"Could not extract canvas data for {response.url}")
                    self.failed_count += 1
                    return

                # Get iframe src for potential direct access
                iframe_src = await iframe_element.get_attribute('src') or ''

                # Save complete HTML to file for backup
                html_filename = f"raw_html/{title_clean}_{url_hash}.html"
                iframe_full_html = await iframe.content()

                with open(f'output/{html_filename}', 'w', encoding='utf-8') as f:
                    f.write(iframe_full_html)

                self.collected_count += 1
                self.logger.info(f"✓ Collected {self.collected_count}: {title_clean}")

                # Yield structured data for JSONL export
                yield {
                    # Identifiers
                    'url': response.url,
                    'url_hash': url_hash,
                    'title': title,
                    'title_clean': title_clean,
                    # Canvas data for rendering
                    'canvas_html': canvas_data['canvasHTML'],
                    'canvas_style': canvas_data['canvasStyle'],
                    'full_html': canvas_data['fullHTML'],
                    'shapes': canvas_data['shapes'],
                    'shape_count': len(canvas_data['shapes']),
                    # Dimensions
                    'width': canvas_data['width'],
                    'height': canvas_data['height'],
                    # Styling
                    'css_links': canvas_data['cssLinks'],
                    'inline_styles': canvas_data['inlineStyles'],
                    # Metadata
                    'view_count': response.xpath(
                        "//span[@class='left_item view_count']//span[@class='count left_item_text']/text()").get(),
                    'clone_count': response.xpath(
                        "//span[@class='left_item view_clone_count']//span[@class='count left_item_text']/text()").get(),
                    'like_count': response.xpath("//span[@class='file_head_right_item like_count']/span[@class='count']/text()").get(),
                    'fav_count': response.xpath(
                        "//div[@class='fav_count file_head_right_item']//span[@class='count']/text()").get(),
                    'description': response.xpath("//div[@class='intro_text']/text()").get(),
                    # Files
                    'iframe_src': iframe_src,
                    'html_file': html_filename,
                }

            except Exception as e:
                self.logger.error(f"Failed to collect data for {response.url}: {str(e)}")
                self.failed_count += 1

        except Exception as e:
            self.logger.error(f"Error parsing {response.url}: {str(e)}")
            self.failed_count += 1
        finally:
            if page:
                try:
                    await page.close()
                except:
                    pass

    def closed(self, reason):
        self.logger.info(f"Spider closed: {reason}")
        self.logger.info(f"Total data collected: {self.collected_count}")
        self.logger.info(f"Total failed: {self.failed_count}")
        self.logger.info(f"Data saved to: output/flowcharts_raw_data.jsonl")
        self.logger.info(f"HTML files saved to: output/raw_html/")