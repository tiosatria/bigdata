"""
Configuration testing utility
Tests domain configurations against live websites
Simulates actual spider behavior including Playwright/Scrapy rendering
"""

import requests
from lxml import html, etree
from typing import Dict, Any, Optional
import logging
from urllib.parse import urljoin, urlparse
import sys

class ConfigTester:
    """Test domain configurations with realistic simulation"""

    def __init__(self, config):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Setup session for Scrapy simulation
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        })

        self.playwright_available = False
        self.playwright = None
        self.browser = None

        # Try to import playwright if needed
        if self.config.render_engine.value == 'playwright':
            try:
                from playwright.sync_api import sync_playwright
                self.playwright_module = sync_playwright
                self.playwright_available = True
            except ImportError:
                self.logger.warning(
                    "⚠️  Playwright not installed but config uses it. "
                    "Install with: pip install playwright && playwright install chromium"
                )

    def test_all(self, test_url: Optional[str] = None, verbose: bool = False) -> Dict[str, Dict[str, Any]]:
        """Run all tests"""
        results = {}

        # Determine test URL
        if test_url:
            url = test_url
        else:
            url = f"https://{self.config.domain}"

        self.logger.info(f"Testing URL: {url}")
        self.logger.info(f"Render engine: {self.config.render_engine.value}")

        # Fetch the page using appropriate method
        try:
            if self.config.render_engine.value == 'playwright' and self.playwright_available:
                response_data = self._fetch_with_playwright(url, verbose)
            else:
                if self.config.render_engine.value == 'playwright' and not self.playwright_available:
                    self.logger.warning("⚠️  Falling back to requests (Playwright not available)")
                response_data = self._fetch_with_requests(url, verbose)

            if not response_data:
                return {
                    'fetch': {
                        'passed': False,
                        'message': f"Failed to fetch page",
                        'data': None
                    }
                }

            tree = html.fromstring(response_data['content'])

        except Exception as e:
            return {
                'fetch': {
                    'passed': False,
                    'message': f"Failed to fetch page: {str(e)}",
                    'data': None
                }
            }

        # Determine if this is a listing page or article page
        page_type = self._detect_page_type(tree, url)

        if verbose:
            print(f"\n📄 Page type detected: {page_type}")

        # Test based on page type
        if page_type == 'listing':
            # Test article links
            results['article_links'] = self._test_article_links(tree, url, verbose)

            # Test pagination (if configured)
            if self.config.pagination_xpath:
                results['pagination'] = self._test_pagination(tree, url, verbose)

        elif page_type == 'article':
            # Test title extraction
            results['title'] = self._test_title(tree, verbose)

            # Test body extraction
            results['body'] = self._test_body(tree, verbose)

            # Test optional fields
            if self.config.author_xpath:
                results['author'] = self._test_author(tree, verbose)

            if self.config.tags_xpath:
                results['tags'] = self._test_tags(tree, verbose)

            if self.config.post_date_xpath:
                results['post_date'] = self._test_post_date(tree, verbose)

        else:
            # Unknown page type - test everything
            results['article_links'] = self._test_article_links(tree, url, verbose)

            if self.config.pagination_xpath:
                results['pagination'] = self._test_pagination(tree, url, verbose)

            results['title'] = self._test_title(tree, verbose)
            results['body'] = self._test_body(tree, verbose)

        return results

    def _fetch_with_requests(self, url: str, verbose: bool) -> Optional[Dict[str, Any]]:
        """Fetch page using requests (simulates Scrapy)"""
        try:
            if verbose:
                print(f"🌐 Fetching with requests (Scrapy simulation)...")

            response = self.session.get(url, timeout=30)
            response.raise_for_status()

            if verbose:
                print(f"✓ Status: {response.status_code}")
                print(f"✓ Content length: {len(response.content)} bytes")

            return {
                'content': response.content,
                'status': response.status_code,
                'url': response.url
            }

        except Exception as e:
            self.logger.error(f"Failed to fetch with requests: {e}")
            return None

    def _fetch_with_playwright(self, url: str, verbose: bool) -> Optional[Dict[str, Any]]:
        """Fetch page using Playwright (simulates Playwright rendering)"""
        try:
            if verbose:
                print(f"🎭 Fetching with Playwright...")

            with self.playwright_module() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        '--disable-blink-features=AutomationControlled',
                        '--disable-dev-shm-usage',
                    ]
                )

                context_kwargs = {
                    'user_agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    'ignore_https_errors': True,
                }

                context = browser.new_context(**context_kwargs)
                page = context.new_page()

                # Wait for selectors if configured
                if self.config.bot_protection.wait_for_selectors:
                    if verbose:
                        print(f"⏳ Waiting for selectors: {self.config.bot_protection.wait_for_selectors}")

                # Navigate to page
                response = page.goto(
                    url,
                    wait_until=self.config.playwright_wait_until,
                    timeout=self.config.playwright_timeout
                )

                # Wait for specific selectors
                if self.config.bot_protection.wait_for_selectors:
                    for selector in self.config.bot_protection.wait_for_selectors:
                        try:
                            page.wait_for_selector(selector, timeout=self.config.playwright_timeout)
                            if verbose:
                                print(f"✓ Found selector: {selector}")
                        except Exception as e:
                            if verbose:
                                print(f"⚠️  Selector not found: {selector}")

                content = page.content()
                final_url = page.url
                status = response.status if response else 200

                browser.close()

                if verbose:
                    print(f"✓ Status: {status}")
                    print(f"✓ Content length: {len(content)} bytes")
                    print(f"✓ Final URL: {final_url}")

                return {
                    'content': content.encode('utf-8'),
                    'status': status,
                    'url': final_url
                }

        except Exception as e:
            self.logger.error(f"Failed to fetch with Playwright: {e}")
            return None

    def _detect_page_type(self, tree, url: str) -> str:
        """Detect if page is a listing page or article page"""

        # Check for article content
        has_title = bool(tree.xpath(self.config.title_xpath))
        has_body = bool(tree.xpath(self.config.body_xpath))

        # Check for article links
        has_article_links = False
        if self.config.article_links_xpath:
            has_article_links = bool(tree.xpath(self.config.article_links_xpath))

        # If has both title and substantial body, likely an article
        if has_title and has_body:
            body_text = tree.xpath(self.config.body_xpath)
            if body_text:
                text_content = body_text[0].text_content().strip()
                if len(text_content) > 500:  # Substantial content
                    return 'article'

        # If has article links, likely a listing page
        if has_article_links:
            return 'listing'

        return 'unknown'

    def _test_article_links(self, tree, base_url: str, verbose: bool) -> Dict[str, Any]:
        """Test article links extraction"""
        try:
            # Handle multiple XPaths
            article_xpaths = self.config.article_links_xpath if isinstance(self.config.article_links_xpath, list) else [self.config.article_links_xpath]

            all_links = []
            xpath_results = {}

            for xpath in article_xpaths:
                if not xpath:
                    continue

                try:
                    links = tree.xpath(xpath)
                    xpath_results[xpath] = len(links)
                    all_links.extend(links)

                    if verbose:
                        print(f"  XPath '{xpath}': found {len(links)} links")
                except Exception as e:
                    xpath_results[xpath] = f"Error: {e}"
                    if verbose:
                        print(f"  XPath '{xpath}': ERROR - {e}")

            if not all_links:
                return {
                    'passed': False,
                    'message': f'No article links found. Tried {len(article_xpaths)} XPath(s)',
                    'data': xpath_results
                }

            # Convert to absolute URLs and deduplicate
            absolute_links = []
            seen = set()
            for link in all_links:
                absolute_url = urljoin(base_url, link)
                if absolute_url not in seen:
                    absolute_links.append(absolute_url)
                    seen.add(absolute_url)

            if verbose:
                print(f"\n📰 Found {len(absolute_links)} unique article links (from {len(all_links)} total)")
                print("Sample links:")
                for link in absolute_links[:3]:
                    print(f"  - {link}")

            return {
                'passed': True,
                'message': f'Found {len(absolute_links)} unique article links from {len(article_xpaths)} XPath(s)',
                'data': {
                    'xpath_results': xpath_results,
                    'sample_links': absolute_links[:5]
                }
            }

        except Exception as e:
            return {
                'passed': False,
                'message': f'XPath error: {str(e)}',
                'data': None
            }

    def _test_pagination(self, tree, base_url: str, verbose: bool) -> Dict[str, Any]:
        """Test pagination links extraction"""
        try:
            links = tree.xpath(self.config.pagination_xpath)

            if not links:
                return {
                    'passed': True,  # Optional feature
                    'message': 'No pagination links found (may be on last page)',
                    'data': None
                }

            # Convert to absolute URLs
            absolute_links = [urljoin(base_url, link) for link in links[:3]]

            if verbose:
                print(f"\n📄 Found {len(links)} pagination links")
                for link in absolute_links:
                    print(f"  - {link}")

            return {
                'passed': True,
                'message': f'Found {len(links)} pagination links',
                'data': absolute_links
            }

        except Exception as e:
            return {
                'passed': False,
                'message': f'XPath error: {str(e)}',
                'data': None
            }

    def _test_title(self, tree, verbose: bool) -> Dict[str, Any]:
        """Test title extraction"""
        try:
            title = tree.xpath(self.config.title_xpath)

            if not title:
                return {
                    'passed': False,
                    'message': f'No title found with XPath: {self.config.title_xpath}',
                    'data': None
                }

            title_text = title[0].strip() if isinstance(title[0], str) else title[0].text_content().strip()

            if not title_text:
                return {
                    'passed': False,
                    'message': 'Title is empty after extraction',
                    'data': None
                }

            if verbose:
                print(f"\n📌 Title: {title_text[:100]}")

            return {
                'passed': True,
                'message': f'Title extracted ({len(title_text)} chars)',
                'data': title_text[:100]
            }

        except Exception as e:
            return {
                'passed': False,
                'message': f'XPath error: {str(e)}',
                'data': None
            }

    def _test_body(self, tree, verbose: bool) -> Dict[str, Any]:
        """Test body content extraction"""
        try:
            body_elements = tree.xpath(self.config.body_xpath)

            if not body_elements:
                return {
                    'passed': False,
                    'message': f'No body content found with XPath: {self.config.body_xpath}',
                    'data': None
                }

            body_element = body_elements[0]
            body_html = etree.tostring(body_element, encoding='unicode', method='html')

            # Get text content for length check
            text_content = body_element.text_content().strip()

            if not text_content:
                return {
                    'passed': False,
                    'message': 'Body content is empty',
                    'data': None
                }

            if len(text_content) < 50:
                return {
                    'passed': False,
                    'message': f'Body content too short ({len(text_content)} chars)',
                    'data': text_content
                }

            if verbose:
                print(f"\n📝 Body content: {len(text_content)} chars")
                print(f"Preview: {text_content[:200]}...")

            return {
                'passed': True,
                'message': f'Body content extracted ({len(text_content)} chars)',
                'data': text_content[:200]
            }

        except Exception as e:
            return {
                'passed': False,
                'message': f'XPath error: {str(e)}',
                'data': None
            }

    def _test_author(self, tree, verbose: bool) -> Dict[str, Any]:
        """Test author extraction"""
        try:
            author = tree.xpath(self.config.author_xpath)

            if not author:
                return {
                    'passed': True,  # Optional
                    'message': 'No author found',
                    'data': None
                }

            author_text = author[0].strip() if isinstance(author[0], str) else author[0].text_content().strip()

            if verbose:
                print(f"\n✍️  Author: {author_text}")

            return {
                'passed': True,
                'message': f'Author extracted: {author_text}',
                'data': author_text
            }

        except Exception as e:
            return {
                'passed': False,
                'message': f'XPath error: {str(e)}',
                'data': None
            }

    def _test_tags(self, tree, verbose: bool) -> Dict[str, Any]:
        """Test tags extraction"""
        try:
            tags = tree.xpath(self.config.tags_xpath)

            if not tags:
                return {
                    'passed': True,  # Optional
                    'message': 'No tags found',
                    'data': None
                }

            tag_list = [tag.strip() if isinstance(tag, str) else tag.text_content().strip() for tag in tags]
            tag_list = [t for t in tag_list if t]  # Remove empty

            if verbose:
                print(f"\n🏷️  Tags: {', '.join(tag_list[:5])}")

            return {
                'passed': True,
                'message': f'Found {len(tag_list)} tags',
                'data': tag_list[:5]
            }

        except Exception as e:
            return {
                'passed': False,
                'message': f'XPath error: {str(e)}',
                'data': None
            }

    def _test_post_date(self, tree, verbose: bool) -> Dict[str, Any]:
        """Test post date extraction"""
        try:
            date = tree.xpath(self.config.post_date_xpath)

            if not date:
                return {
                    'passed': True,  # Optional
                    'message': 'No post date found',
                    'data': None
                }

            date_text = date[0].strip() if isinstance(date[0], str) else date[0].text_content().strip()

            # Try to parse if format provided
            parsed_date = None
            if self.config.post_date_format:
                try:
                    from datetime import datetime
                    parsed_date = datetime.strptime(date_text, self.config.post_date_format)

                    if verbose:
                        print(f"\n📅 Post date: {date_text} -> {parsed_date}")

                    return {
                        'passed': True,
                        'message': f'Date parsed successfully: {parsed_date}',
                        'data': str(parsed_date)
                    }
                except ValueError as e:
                    return {
                        'passed': False,
                        'message': f'Date format mismatch: {str(e)}',
                        'data': date_text
                    }

            if verbose:
                print(f"\n📅 Post date: {date_text}")

            return {
                'passed': True,
                'message': f'Date extracted: {date_text}',
                'data': date_text
            }

        except Exception as e:
            return {
                'passed': False,
                'message': f'XPath error: {str(e)}',
                'data': None
            }