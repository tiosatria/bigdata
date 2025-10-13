"""
Test spider simulator
Simulates the actual spider behavior for testing configurations
"""

import json
import tempfile
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, List
import logging

from bigdata.util.config_tester import ConfigTester


class TestSpiderSimulator:
    """Simulates spider behavior for testing"""

    def __init__(self, config, output_dir=None):
        self.config = config
        self.output_dir = Path(output_dir) if output_dir else Path(tempfile.mkdtemp())
        self.output_file = self.output_dir / f"test_{config.domain.replace('.', '_')}.jsonl"
        self.logger = logging.getLogger(__name__)

        self.stats = {
            'urls_tested': 0,
            'articles_extracted': 0,
            'pagination_found': 0,
            'article_links_found': 0,
            'errors': []
        }

    def run_test(self, test_urls: List[Dict[str, str]], verbose=False) -> Dict[str, Any]:
        """
        Run spider simulation test

        Args:
            test_urls: List of {'type': 'listing'|'article', 'url': 'https://...'}
            verbose: Print detailed output

        Returns:
            Test results with statistics and assertions
        """

        if verbose:
            print(f"\n{'=' * 60}")
            print(f"🕷️  Spider Simulation Test: {self.config.domain}")
            print(f"   Output file: {self.output_file}")
            print(f"   Render engine: {self.config.render_engine.value}")
            print(f"{'=' * 60}\n")

        tester = ConfigTester(self.config)
        results = []

        for test_spec in test_urls:
            url_type = test_spec.get('type', 'auto')
            url = test_spec['url']

            self.stats['urls_tested'] += 1

            if verbose:
                print(f"\n🔍 Testing {url_type} page: {url}")
                print("-" * 60)

            try:
                # Fetch and parse
                if self.config.render_engine.value == 'playwright' and tester.playwright_available:
                    response_data = tester._fetch_with_playwright(url, verbose)
                else:
                    response_data = tester._fetch_with_requests(url, verbose)

                if not response_data:
                    self.stats['errors'].append(f"Failed to fetch {url}")
                    continue

                from lxml import html as lxml_html
                tree = lxml_html.fromstring(response_data['content'])

                # Determine page type
                page_type = tester._detect_page_type(tree, url)

                if verbose:
                    print(f"   Detected page type: {page_type}")

                # Test based on page type
                if page_type == 'listing' or url_type == 'listing':
                    result = self._test_listing_page(tree, url, tester, verbose)
                elif page_type == 'article' or url_type == 'article':
                    result = self._test_article_page(tree, url, tester, verbose)
                else:
                    result = self._test_unknown_page(tree, url, tester, verbose)

                result['url'] = url
                result['type'] = url_type
                result['detected_type'] = page_type
                results.append(result)

            except Exception as e:
                error_msg = f"Error testing {url}: {e}"
                self.stats['errors'].append(error_msg)
                self.logger.error(error_msg, exc_info=True)

                if verbose:
                    print(f"   ❌ ERROR: {e}")

        # Generate assertions
        assertions = self._generate_assertions(results, verbose)

        # Write summary
        summary = {
            'domain': self.config.domain,
            'test_time': datetime.now().isoformat(),
            'stats': self.stats,
            'results': results,
            'assertions': assertions,
            'output_file': str(self.output_file)
        }

        return summary

    def _test_listing_page(self, tree, url, tester, verbose) -> Dict[str, Any]:
        """Test listing page functionality"""
        result = {
            'article_links': None,
            'pagination': None
        }

        # Test article links
        article_result = tester._test_article_links(tree, url, verbose)
        result['article_links'] = article_result

        if article_result['passed'] and article_result.get('data'):
            data = article_result['data']
            if isinstance(data, dict) and 'sample_links' in data:
                self.stats['article_links_found'] += len(data['sample_links'])
            elif isinstance(data, list):
                self.stats['article_links_found'] += len(data)

        # Test pagination
        if self.config.pagination_xpath:
            pagination_result = tester._test_pagination(tree, url, verbose)
            result['pagination'] = pagination_result

            if pagination_result['passed'] and pagination_result.get('data'):
                data = pagination_result['data']
                if isinstance(data, dict) and 'sample_links' in data:
                    if data['sample_links']:
                        self.stats['pagination_found'] += len(data['sample_links'])
                elif isinstance(data, list):
                    self.stats['pagination_found'] += len(data)

        return result

    def _test_article_page(self, tree, url, tester, verbose) -> Dict[str, Any]:
        """Test article page extraction"""
        result = {
            'title': None,
            'body': None,
            'author': None,
            'tags': None,
            'post_date': None
        }

        # Test title
        title_result = tester._test_title(tree, verbose)
        result['title'] = title_result

        # Test body
        body_result = tester._test_body(tree, verbose)
        result['body'] = body_result

        # Test optional fields
        if self.config.author_xpath:
            result['author'] = tester._test_author(tree, verbose)

        if self.config.tags_xpath:
            result['tags'] = tester._test_tags(tree, verbose)

        if self.config.post_date_xpath:
            result['post_date'] = tester._test_post_date(tree, verbose)

        # If article extracted successfully, save to output file
        if title_result['passed'] and body_result['passed']:
            self.stats['articles_extracted'] += 1
            self._save_article(url, result)

        return result

    def _test_unknown_page(self, tree, url, tester, verbose) -> Dict[str, Any]:
        """Test page with unknown type"""
        result = {}

        # Test everything
        result['article_links'] = tester._test_article_links(tree, url, verbose)

        if self.config.pagination_xpath:
            result['pagination'] = tester._test_pagination(tree, url, verbose)

        result['title'] = tester._test_title(tree, verbose)
        result['body'] = tester._test_body(tree, verbose)

        return result

    def _save_article(self, url, result):
        """Save extracted article to output file"""
        try:
            article_data = {
                'url': url,
                'domain': self.config.domain,
                'title': result['title'].get('data') if result['title']['passed'] else None,
                'body_length': len(result['body'].get('data', '')) if result['body']['passed'] else 0,
                'author': result.get('author', {}).get('data') if result.get('author') else None,
                'tags': result.get('tags', {}).get('data') if result.get('tags') else None,
                'post_date': result.get('post_date', {}).get('data') if result.get('post_date') else None,
                'extracted_at': datetime.now().isoformat()
            }

            with open(self.output_file, 'a', encoding='utf-8') as f:
                f.write(json.dumps(article_data, ensure_ascii=False) + '\n')

        except Exception as e:
            self.logger.error(f"Failed to save article: {e}")

    def _generate_assertions(self, results, verbose) -> Dict[str, Any]:
        """Generate test assertions"""
        assertions = {
            'passed': True,
            'checks': []
        }

        # Check 1: At least one URL was tested
        check1 = {
            'name': 'URLs tested',
            'passed': self.stats['urls_tested'] > 0,
            'expected': '>= 1',
            'actual': self.stats['urls_tested']
        }
        assertions['checks'].append(check1)
        if not check1['passed']:
            assertions['passed'] = False

        # Check 2: Article links found (if listing pages tested)
        listing_pages = [r for r in results if r.get('detected_type') == 'listing' or r.get('type') == 'listing']
        if listing_pages:
            check2 = {
                'name': 'Article links found on listing pages',
                'passed': self.stats['article_links_found'] > 0,
                'expected': '> 0',
                'actual': self.stats['article_links_found']
            }
            assertions['checks'].append(check2)
            if not check2['passed']:
                assertions['passed'] = False

        # Check 3: Articles extracted (if article pages tested)
        article_pages = [r for r in results if r.get('detected_type') == 'article' or r.get('type') == 'article']
        if article_pages:
            check3 = {
                'name': 'Articles successfully extracted',
                'passed': self.stats['articles_extracted'] > 0,
                'expected': '> 0',
                'actual': self.stats['articles_extracted']
            }
            assertions['checks'].append(check3)
            if not check3['passed']:
                assertions['passed'] = False

        # Check 4: Required fields extracted
        if article_pages:
            title_success = sum(1 for r in results if r.get('title', {}).get('passed', False))
            body_success = sum(1 for r in results if r.get('body', {}).get('passed', False))

            check4 = {
                'name': 'Required fields (title & body) extracted',
                'passed': title_success > 0 and body_success > 0,
                'expected': 'All article pages',
                'actual': f"{title_success} titles, {body_success} bodies"
            }
            assertions['checks'].append(check4)
            if not check4['passed']:
                assertions['passed'] = False

        # Check 5: No critical errors
        check5 = {
            'name': 'No critical errors',
            'passed': len(self.stats['errors']) == 0,
            'expected': '0 errors',
            'actual': f"{len(self.stats['errors'])} errors"
        }
        assertions['checks'].append(check5)
        if not check5['passed']:
            assertions['passed'] = False

        # Check 6: Output file created (if articles extracted)
        if self.stats['articles_extracted'] > 0:
            check6 = {
                'name': 'Output file created',
                'passed': self.output_file.exists(),
                'expected': 'File exists',
                'actual': str(self.output_file) if self.output_file.exists() else 'Not created'
            }
            assertions['checks'].append(check6)
            if not check6['passed']:
                assertions['passed'] = False

        if verbose:
            print(f"\n{'=' * 60}")
            print("✅ ASSERTIONS" if assertions['passed'] else "❌ ASSERTIONS")
            print(f"{'=' * 60}")
            for check in assertions['checks']:
                status = "✓" if check['passed'] else "✗"
                print(f"{status} {check['name']}")
                print(f"   Expected: {check['expected']}")
                print(f"   Actual: {check['actual']}")

        return assertions

    def get_output_file(self) -> Path:
        """Get the output file path"""
        return self.output_file

    def read_output(self) -> List[Dict[str, Any]]:
        """Read extracted articles from output file"""
        if not self.output_file.exists():
            return []

        articles = []
        with open(self.output_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    articles.append(json.loads(line))

        return articles