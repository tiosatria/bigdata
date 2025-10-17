import re
from datetime import datetime
from typing import Optional, Iterable
from lxml import html, etree
from scrapy import Spider

from bigdata.domain_configs.domain_config import CustomParser, OBVIOUS_EXCLUDES
from bigdata.items import ArticleItem


class GenericAutoParser(CustomParser):
    """
    Heuristics-based article extractor used when no DomainConfig is provided.

    Goals:
    - High detection quality with low false positives
    - No per-site XPath required
    - Keep output aligned with ArticleItem fields
    """

    # Common URL patterns that tend to be article/content pages
    DEFAULT_ARTICLE_URL_PATTERNS = [
        r"/\d{4}/\d{1,2}/\d{1,2}/",   # dated URLs (YYYY/MM/DD)
        r"/\d{4}/\d{1,2}/",            # dated URLs (YYYY/MM)
        r"/[a-z0-9-]+-\d{6,}(?:/|$)",   # slug with numeric id at the end (e.g., kinja-style)
        r"/(news|article|story|post|blog|recipe|how-to|howto|guide|guides|feature|features|review|opinion|interview)s?(?:/|$|-)",
        r"/[a-z0-9-]{30,}(?:/|$)",       # long sluggy URLs (no trailing slash required)
    ]

    # Patterns to ignore
    DEFAULT_DENY_PATTERNS = [
        r"/login|/signin|/signup|/register|/account|/cart|/checkout",
        r"\.(jpg|jpeg|png|gif|svg|css|js|ico|mp4|mp3|zip|rar|7z|pdf)(\?|$)",
    ]

    def __init__(self, min_body_chars: int = 200):
        self.min_body_chars = min_body_chars
        # Compile regexes for efficiency
        self.deny_patterns = [re.compile(p, re.I) for p in self.DEFAULT_DENY_PATTERNS]
        self.article_patterns = [re.compile(p, re.I) for p in self.DEFAULT_ARTICLE_URL_PATTERNS]

    def _is_article_url(self, url: str) -> bool:
        """
        Checks URL against deny and article patterns.
        This is a first-pass filter.
        """
        for pat in self.deny_patterns:
            if pat.search(url):
                return False  # Explicitly denied (e.g., /login)

        for pat in self.article_patterns:
            if pat.search(url):
                return True  # Matches a known article pattern

        # If it's not denied but also doesn't match a good
        # article pattern, reject it. This stops homepages (/)
        # and simple pages like /about-us.
        return False

    def parse_item(self, response, config, spider: Spider):
        if not self._is_article_url(response.url):
            spider.logger.debug(f"✗ Skipping parsing non-article URL pattern: {response.url}")
            return

        title = self._extract_title(response)
        body_html = self._extract_body_html(response)

        if not title or not body_html:
            spider.logger.warning(
                f"Possibly Not a content. no {'Title' if not title else 'Body'} was found for {response.url}.")
            return

        cleaned_html = self._clean_html(body_html)
        # Ensure the minimum body length check uses only core, tag-stripped article text (no HTML/artifacts)
        if not cleaned_html or len(self._core_text_only(cleaned_html)) < self.min_body_chars:
            spider.logger.debug(f"✗ skipped, below min text length not met. {cleaned_html}: {response.url}")
            return

        source = self._domain(response.url)

        author = self._extract_author(response)
        post_date = self._extract_post_date(response)
        tags = self._extract_tags(response)
        lang = self._extract_lang(response)

        spider.logger.info(f"✓ Successfully scraped: {title[:90]}... from generic parsing mode site: ({source})")

        yield ArticleItem(
            url=response.url,
            source_domain=source,
            title=title.strip(),
            tags=tags,
            author=author,
            post_date=post_date,
            body=cleaned_html,
            body_type="html",
            lang=lang or "en",
            timestamp=datetime.now(),
        )

    # -------- helpers ---------
    @staticmethod
    def _domain(url: str) -> str:
        from urllib.parse import urlparse
        return urlparse(url).netloc.replace("www.", "")

    def _extract_title(self, response) -> Optional[str]:
        candidates = [
            response.xpath("//h1//text()").get(),
            response.xpath("//title/text()").get(),
            response.xpath("//meta[@property='og:title']/@content").get(),
            response.xpath("//meta[@name='twitter:title']/@content").get(),
            response.xpath("//meta[@name='parsely-title']/@content").get(),
        ]
        for t in candidates:
            if t and t.strip():
                return t.strip()
        return None

    def _extract_body_html(self, response) -> Optional[str]:
        container_xpaths: Iterable[str] = [
            "//article",
            "//main//*[self::article or contains(@class,'content') or contains(@id,'content')]",
            "//div[contains(@class,'article') or contains(@class,'post') or contains(@class,'entry') or contains(@class,'story') or contains(@id,'article') or contains(@id,'post')]",
        ]

        nodes = []
        for xp in container_xpaths:
            try:
                res = response.xpath(xp)
                if res:
                    nodes.extend(res)
            except Exception:
                continue

        if not nodes:
            nodes = response.xpath("//div | //section | //main | //article")

        best_node = None
        best_score = float('-inf')

        for n in nodes:
            try:
                p_texts = n.xpath('.//p//text()')
                text = ' '.join(t.strip() for t in p_texts if t and t.strip())
                text_len = len(text)
                p_count = len(n.xpath('.//p'))
                link_count = len(n.xpath('.//a'))
                nav_penalty = len(n.xpath('.//nav | .//aside | .//*[@role=\"navigation\"]'))
                li_count = len(n.xpath('.//li'))

                score = text_len + (100 * p_count) - (50 * link_count) - (150 * nav_penalty) - (li_count * 10)
                if text_len < 150:
                    score -= 1000

                if score > best_score:
                    best_score = score
                    best_node = n
            except Exception:
                continue

        # fallback: collect all <p> nodes and merge them into a div
        if not best_node or best_score < 500:
            paras = response.xpath('//p[not(ancestor::nav) and not(ancestor::aside)]')
            if paras:
                wrapper = etree.Element("div")
                for p in paras:
                    try:
                        wrapper.append(p.root if hasattr(p, "root") else p)
                    except Exception:
                        continue
                return etree.tostring(wrapper, encoding="unicode", method="html")

        if best_node is None:
            return None

        try:
            return etree.tostring(best_node.root if hasattr(best_node, "root") else best_node,
                                  encoding="unicode", method="html")
        except Exception:
            try:
                return best_node.get()
            except Exception:
                return None

    def _clean_html(self, fragment: str) -> str:
        if not fragment:
            return ""
        try:
            doc = html.fromstring(fragment)
            for xp in OBVIOUS_EXCLUDES:
                try:
                    for node in doc.xpath(xp):
                        parent = node.getparent()
                        if parent is not None:
                            parent.remove(node)
                except Exception:
                    pass
            return etree.tostring(doc, encoding="unicode", method="html")
        except Exception:
            return fragment

    def _extract_author(self, response) -> Optional[str]:
        texts: list[str] = []
        author_meta = response.xpath("//meta[@name='author']/@content").get()
        if author_meta:
            texts.append(author_meta)
        # Collect visible byline/author text nodes as strings
        byline_texts = response.xpath(
            "//*[contains(@class,'author') or contains(@class,'byline')]/descendant-or-self::text()"
        ).getall() or []
        for t in byline_texts:
            if t:
                texts.append(t)
        for s in texts:
            t = s.strip()
            if len(t) < 3:
                continue
            # Clean common prefixes
            t = re.sub(r"^by\s+", "", t, flags=re.I)
            if t:
                return t
        return None

    def _extract_post_date(self, response) -> Optional[str]:
        candidates = [
            response.xpath("//meta[@property='article:published_time']/@content").get(),
            response.xpath("//time/@datetime").get(),
            response.xpath("//time/text()").get(),
        ]
        for c in candidates:
            if c and c.strip():
                return c.strip()
        # try URL
        m = re.search(r"/(20\d{2})/(\d{1,2})/(\d{1,2})/", response.url)
        if m:
            return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
        return None

    def _extract_tags(self, response) -> list:
        tags = response.xpath(
            "//a[contains(@href,'tag') or contains(@class,'tag') or contains(@class,'breadcrumb')]/text() | "
            "//ul[contains(@class,'breadcrumb')]/li/a/text()"
        ).getall() or []
        return [t.strip() for t in tags if t and t.strip()]

    def _extract_lang(self, response) -> Optional[str]:
        return (response.xpath('//html/@lang').get() or '').split('-')[0] or 'en'

    @staticmethod
    def _text_only(html_fragment: str) -> str:
        try:
            doc = html.fromstring(html_fragment)
            texts = doc.xpath('//text()')
            return ' '.join([t.strip() for t in texts if t and t.strip()])
        except Exception:
            return html_fragment or ""

    @staticmethod
    def _core_text_only(html_fragment: str) -> str:
        """
        Extract only core article text from typical content elements (paragraphs, headings, and list items),
        excluding any HTML/tags and avoiding peripheral artifacts (menus, breadcrumbs, etc.).
        This is used for enforcing GENERIC_MIN_BODY_CHARS.
        """
        try:
            doc = html.fromstring(html_fragment)
            # Focus on paragraphs, subheadings, and list items inside the content
            texts = doc.xpath('//p//text() | //h2//text() | //h3//text() | //h4//text() | //h5//text() | //h6//text() | //li//text()')
            return ' '.join([t.strip() for t in texts if t and t.strip()])
        except Exception:
            return ''
