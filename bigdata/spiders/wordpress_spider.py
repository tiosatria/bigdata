from typing import AsyncIterator, Any, Dict, Iterable
import csv
import json
import uuid
from urllib.parse import urlparse, urlunparse

import scrapy

from bigdata.items import CrawlItem


class WordpressSpider(scrapy.Spider):
    name = 'wordpress'

    def __init__(self,
                 csv_path=None,
                 site_list=None,
                 sites=None,
                 site=None,
                 text=None,
                 disable_proxy=None,
                 *args,
                 **kwargs):
        # Support multiple input methods:
        # - csv_path: path to CSV file with columns: url, use_proxy (optional), bypass_cf (optional)
        # - site_list or text: path to .txt with one site per line; will force use_proxy=True
        # - sites or site: semicolon-separated list of sites/urls
        if not any([csv_path, site_list, sites, site, text]):
            raise ValueError('Provide at least one of: csv_path, site_list, sites')
        self.csv_path = csv_path
        # aliasing
        self.site_list = site_list or text
        self.disable_proxy = disable_proxy
        self.sites_arg = sites or site
        super().__init__(*args, **kwargs)

    custom_settings = {
        'CONCURRENT_REQUESTS' : 100,
        'CONCURRENT_REQUESTS_PER_DOMAIN' : 8,
        'DOWNLOAD_DELAY': 1,
        # 'AUTOTHROTTLE_ENABLED': True,
        'MAX_RETRY_FAILED': 10,
        'RETRY_TIMES': 10
    }

    def _parse_bool(self, v) -> bool:
        if isinstance(v, bool):
            return v
        if v is None:
            return False
        s = str(v).strip().lower()
        return s in {'1', 'true', 'yes', 'y', 't'}

    def _build_wp_posts_url(self, base_url: str, page: int = 1, per_page: int = 100) -> str:
        # Normalize to scheme+netloc
        p = urlparse(base_url)
        scheme = p.scheme or 'https'
        netloc = p.netloc or p.path  # handle inputs like example.com
        base = urlunparse((scheme, netloc, '', '', '', ''))
        # WordPress REST posts endpoint
        path = '/wp-json/wp/v2/posts'
        query = f'per_page={per_page}&page={page}'
        return f"{base}{path}?{query}"

    def _default_headers(self) -> Dict[str, str]:
        return {
            'Accept': 'application/json, text/javascript, */*; q=0.1',
            'Accept-Language': 'en-US,en;q=0.8',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
            'Cache-Control': 'no-cache',
        }

    def _parse_json_response(self, response: scrapy.http.Response):
        # Try robust JSON parsing handling BOM and charset
        # 1) Try declared encoding
        body = response.body or b''
        # Fast path: response.text when non-empty
        txt = (response.text or '').strip()
        if txt:
            return json.loads(txt)
        # Try charset from Content-Type
        ctype = response.headers.get(b'Content-Type') or response.headers.get(b'content-type')
        charset = None
        if ctype:
            try:
                cts = ctype.decode() if isinstance(ctype, (bytes, bytearray)) else str(ctype)
                for part in cts.split(';'):
                    part = part.strip()
                    if part.lower().startswith('charset='):
                        charset = part.split('=', 1)[1].strip()
                        break
            except Exception:
                charset = None
        encodings = []
        if charset:
            encodings.append(charset)
        # Common fallbacks
        encodings.extend(['utf-8-sig', 'utf-8', 'latin-1'])
        for enc in encodings:
            try:
                return json.loads(body.decode(enc))
            except Exception:
                continue
        # Last resort: attempt to strip BOM manually then load
        try:
            return json.loads(body.decode('utf-8', errors='strict').lstrip('\ufeff'))
        except Exception:
            # re-raise to caller for logging
            raise

    async def start(self) -> AsyncIterator[Any]:
        # Build a merged set of sites from: csv_path, site_list (or text), and sites string
        sources: Dict[str, Dict[str, Any]] = {}

        def add_site(url_like: str, use_proxy: bool = False, bypass_cf: bool = False):
            if not url_like:
                return
            url_like = url_like.strip()
            if not url_like:
                return
            # Normalize to site key (domain)
            p = urlparse(url_like if urlparse(url_like).scheme else f'https://{url_like}')
            site_key = p.netloc or p.path
            if not site_key:
                return
            info = sources.get(site_key) or {'use_proxy': False, 'bypass_cf': False}
            info['use_proxy'] = bool(info['use_proxy'] or use_proxy)
            info['bypass_cf'] = bool(info['bypass_cf'] or bypass_cf)
            sources[site_key] = info

        # 1) CSV mode
        if self.csv_path:
            try:
                with open(self.csv_path, newline='', encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        url = (row.get('url') or '').strip()
                        if not url:
                            self.logger.warning('Skipping CSV row without url: %r', row)
                            continue
                        use_proxy = self._parse_bool(row.get('use_proxy'))
                        bypass_cf = self._parse_bool(row.get('bypass_cf'))
                        add_site(url, use_proxy=self.disable_proxy if self.disable_proxy is not None else use_proxy, bypass_cf=bypass_cf)
            except FileNotFoundError:
                self.logger.error(f"CSV file not found: {self.csv_path}")
            except Exception as e:
                self.logger.error(f"Failed to read CSV {self.csv_path}: {e}")

        # 2) .txt list mode (site_list or text) -> force use_proxy=True
        if self.site_list:
            try:
                with open(self.site_list, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith('#'):
                            continue
                        # For entries from txt, force use_proxy = True
                        add_site(line, use_proxy=self.disable_proxy if self.disable_proxy is not None else True, bypass_cf=False)
            except FileNotFoundError:
                self.logger.error(f"Site list file not found: {self.site_list}")
            except Exception as e:
                self.logger.error(f"Failed to read site list {self.site_list}: {e}")

        # 3) Direct sites string (semicolon-separated)
        if self.sites_arg:
            for part in str(self.sites_arg).split(';'):
                add_site(part.strip(), use_proxy=self.disable_proxy if self.disable_proxy is not None else True, bypass_cf=False)

        if not sources:
            self.logger.error('No sites to crawl after processing inputs.')
            return

        # Emit initial requests for each unique site
        for site, flags in sources.items():
            api_url = self._build_wp_posts_url(site, page=1)
            meta: Dict[str, Any] = {
                'site': site,
                'use_proxy': bool(flags.get('use_proxy')),
                'bypass_cf': bool(flags.get('bypass_cf')),
                'is_start_url': True,
                'body_type': 'json/wordpress',
                'wp_current_page': 1,
            }
            yield scrapy.Request(api_url,
                                 meta=meta,
                                 headers=self._default_headers(),
                                 dont_filter=True,
                                 callback=self.parse_wp_posts)

    def _validate_wp_headers(self, response: scrapy.http.Response) -> Dict[str, int]:
        total_pages_hdr = response.headers.get(b'X-WP-TotalPages') or response.headers.get(b'x-wp-totalpages')
        total_hdr = response.headers.get(b'X-WP-Total') or response.headers.get(b'x-wp-total')
        if not total_pages_hdr or not total_hdr:
            raise scrapy.exceptions.IgnoreRequest(
                f"Not a WordPress posts endpoint (missing headers) for site {response.meta.get('site')}: {response.url}")
        try:
            total_pages = int(total_pages_hdr.decode() if isinstance(total_pages_hdr, (bytes, bytearray)) else total_pages_hdr)
            total = int(total_hdr.decode() if isinstance(total_hdr, (bytes, bytearray)) else total_hdr)
        except Exception:
            raise scrapy.exceptions.IgnoreRequest(
                f"Invalid WordPress headers for site {response.meta.get('site')}: {response.url}")
        return {'total_pages': total_pages, 'total': total}

    def schedule_remaining_pages(self, response: scrapy.http.Response, total_pages: int) -> Iterable[scrapy.Request]:
        meta = response.meta.copy()
        # Only schedule from first page to avoid duplicates
        current_page = int(meta.get('wp_current_page') or 1)
        if current_page != 1:
            return None
        site = meta.get('site')
        # Build and yield requests for pages 2..N
        base_url_from_request = response.url.split('?')[0]
        for page in range(2, total_pages + 1):
            api_url = f"{base_url_from_request}?per_page=100&page={page}"
            m = meta.copy()
            m['wp_current_page'] = page

            yield scrapy.Request(api_url,
                                 meta=m,
                                 headers=self._default_headers(),
                                 callback=self.parse_wp_posts,
                                 dont_filter=True)
        return None

    def parse_wp_posts(self, response: scrapy.http.Response):
        # Validate headers to confirm WordPress
        try:
            stats = self._validate_wp_headers(response)
        except scrapy.exceptions.IgnoreRequest as e:
            # Log error for this site and stop only this branch
            self.logger.error(str(e))
            return

        # Parse JSON array of posts
        try:
            data = self._parse_json_response(response)
            if not isinstance(data, list):
                raise ValueError('Response JSON is not a list')
        except Exception as e:
            ctype = response.headers.get(b'Content-Type') or response.headers.get(b'content-type')
            clen = len(response.body or b'')
            snippet = (response.text or '')[:200].replace('\n', ' ').replace('\r', ' ')
            self.logger.error('Failed parsing JSON for site %s url %s (status=%s, ctype=%s, bytes=%d, snippet=%r): %s',
                              response.meta.get('site'), response.url, response.status,
                              (ctype.decode() if isinstance(ctype, (bytes, bytearray)) else ctype),
                              clen, snippet, e)
            return

        # schedule other pages if on first page
        for req in self.schedule_remaining_pages(response, stats['total_pages']):
            yield req

        # yield items
        site = response.meta.get('site')
        for post in data:
            try:
                post_url = post.get('link') or post.get('guid', {}).get('rendered') or f"{response.url.split('/wp-json/')[0]}/?p={post.get('id')}"
            except Exception:
                post_url = response.url
            item_meta = response.meta.copy()
            item_meta['body_type'] = 'json/wordpress'
            item_meta['site'] = site

            yield CrawlItem(
                url=post_url,
                id=uuid.uuid4(),
                meta=item_meta,
                body=json.dumps(post, ensure_ascii=False)
            )

        self.logger.info(f'Successfully parsed post result from {response.url} ✅.')