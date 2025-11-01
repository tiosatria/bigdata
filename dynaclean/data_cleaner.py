#!/usr/bin/env python3
"""
OPTIMIZED High-Performance Data Cleaning Pipeline
Maximum concurrency, single-file focus, instant startup
"""

import json
import re
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed
from multiprocessing import cpu_count, Manager
import sys
import time
from queue import Queue
from threading import Thread

import yaml
from uuid import uuid4
from collections import Counter

# Optional progress bars
try:
    from tqdm.auto import tqdm
except Exception:
    tqdm = None

try:
    from trafilatura import extract
    from trafilatura.settings import use_config
    import trafilatura.utils
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing required packages. Install with:")
    print("pip install trafilatura beautifulsoup4 lxml pyyaml")
    sys.exit(1)

# ============================================================================
# DATA CLASSES (unchanged)
# ============================================================================

@dataclass
class ProcessingStats:
    """Thread-safe statistics tracker"""
    total: int = 0
    processed: int = 0
    filtered_pre: int = 0
    filtered_post: int = 0
    failed: int = 0
    success: int = 0

    def to_dict(self):
        return {
            'total': self.total,
            'processed': self.processed,
            'success': self.success,
            'failed': self.failed,
            'filtered_pre': self.filtered_pre,
            'filtered_post': self.filtered_post,
            'success_rate': f"{(self.success / self.total * 100):.2f}%" if self.total > 0 else "0%"
        }


@dataclass
class CleaningConfig:
    """Configuration for cleaning pipeline"""
    delivery_version: str = 'v1'
    domain_fallback: str = 'daily life'
    subdomain_fallback: str = 'living'
    type_fallback: str = 'article'
    pre_filter: Dict = field(default_factory=dict)
    clean: Dict = field(default_factory=dict)
    post_filter: Dict = field(default_factory=dict)
    domain_override: Optional[str] = None
    subdomain_override: Optional[str] = None


# ============================================================================
# CONFIGURATION LOADER (unchanged)
# ============================================================================

class ConfigLoader:
    """Loads and manages YAML configuration"""

    def __init__(self, config_path: str = 'cleaning_map.yaml'):
        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self) -> Dict:
        """Load YAML configuration file"""
        if not self.config_path.exists():
            logging.warning(f"Config file {self.config_path} not found, using defaults")
            return self._default_config()

        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                data = yaml.safe_load(f)
                if not isinstance(data, dict) or not data:
                    logging.warning(f"Config file {self.config_path} is empty or invalid, using defaults")
                    return self._default_config()
                return data
        except Exception as e:
            logging.error(f"Failed to load config {self.config_path}: {e}. Using defaults.")
            return self._default_config()

    def _default_config(self) -> Dict:
        """Default configuration"""
        return {
            'template_wordpress': {
                'delivery_version': 'v1',
                'domain_fallback': 'daily life',
                'subdomain_fallback': 'living',
                'type_fallback': 'article',
                'pre_filter': {
                    're_url': ['/contact/', '/about/'],
                    'body_length': 200
                },
                'clean': {
                    'enabled': [
                        'clean_html', 'clean_title', 'clean_emoji',
                        'clean_whitespace', 'anonymization', 'clean_punctuation',
                        'english_only'
                    ],
                    'args': {
                        'body_xpath': None,
                        'noises': ['//script', '//aside'],
                        'formating': {
                            'retain_table': True,
                            'retain_image': True,
                            'retain_links': False
                        },
                        'pre_html': {
                            'strip_begin_regex': [
                                '(?:(?:<em[^>]*>[^<]{0,100}</em>\\s*){3,})',
                                '<div[^>]*class=["\'](?:breadcrumb|breadcrumbs|site-banner|top-bar)["\'][^>]*>.*?</div>'
                            ],
                            'strip_end_regex': [
                                '<div[^>]*class=["\'](?:related-posts|post-navigation|footer-widgets)["\'][^>]*>.*?</div>',
                                '<footer[^>]*class=["\'](?:site-footer|footer)["\'][^>]*>.*?</footer>'
                            ],
                            'strip_any_regex': [
                                '<div[^>]*class=["\'](?:share|social|newsletter|subscribe|cookie|gdpr)[^"\']*["\'][^>]*>.*?</div>',
                                '<aside[^>]*>.*?</aside>'
                            ]
                        }
                    }
                },
                'post_filter': {
                    're_cleaned_text': ['.*nsfw.*'],
                    're_title': ['.*video.*', '.*review.*', '.*podcast.*'],
                    'domain_containing': ['news', 'blog'],
                    'subdomain_containing': ['entertainment']
                }
            },
            'site_mapping': {},
            'domain_mapping': {}
        }

    def get_site_config(self, sitekey: str) -> CleaningConfig:
        """Get configuration for specific site"""
        site_mapping = self.config.get('site_mapping') or {}
        if not isinstance(site_mapping, dict):
            site_mapping = {}
        site_config = site_mapping.get(sitekey) or {}
        if not isinstance(site_config, dict):
            site_config = {}

        clean_section = site_config.get('clean') or {}
        if not isinstance(clean_section, dict):
            clean_section = {}
        template_name = clean_section.get('type', 'template_wordpress')
        template_root = self.config if isinstance(self.config, dict) else {}
        template = template_root.get(template_name) or template_root.get('template_wordpress') or {}
        if not isinstance(template, dict):
            template = {}

        merged = self._merge_configs(template, site_config)

        pre_filter = merged.get('pre_filter') or {}
        if not isinstance(pre_filter, dict):
            pre_filter = {}
        clean = merged.get('clean') or {}
        if not isinstance(clean, dict):
            clean = {}
        post_filter = merged.get('post_filter') or {}
        if not isinstance(post_filter, dict):
            post_filter = {}

        return CleaningConfig(
            delivery_version=merged.get('delivery_version', 'v1'),
            domain_fallback=merged.get('domain_fallback', 'daily life'),
            subdomain_fallback=merged.get('subdomain_fallback', 'living'),
            type_fallback=merged.get('type_fallback', 'article'),
            pre_filter=pre_filter,
            clean=clean,
            post_filter=post_filter,
            domain_override=site_config.get('domain_override'),
            subdomain_override=site_config.get('subdomain_override')
        )

    def _merge_configs(self, template: Dict, override: Dict) -> Dict:
        """Deep merge two config dictionaries. None values in override are ignored."""
        result = (template or {}).copy() if isinstance(template, dict) else {}
        if not isinstance(override, dict):
            return result

        for key, value in override.items():
            if value is None:
                continue
            base_val = result.get(key)
            if isinstance(base_val, dict) and isinstance(value, dict):
                result[key] = self._merge_configs(base_val, value)
            else:
                result[key] = value

        return result

    @staticmethod
    def _normalize_domain(domain: str) -> str:
        """Normalize domain: strip scheme/port/path, lower, remove leading www."""
        if not domain:
            return ''
        d = domain.strip().lower()
        d = re.sub(r'^https?://', '', d)
        d = d.split('/')[0]
        d = d.split(':')[0]
        if d.startswith('www.'):
            d = d[4:]
        return d

    @staticmethod
    def _base_domain(domain: str) -> str:
        """Approximate registrable base domain (handles common SLDs)."""
        d = ConfigLoader._normalize_domain(domain)
        if not d:
            return ''
        parts = d.split('.')
        if len(parts) <= 2:
            return d
        slds = {('co', 'uk'), ('org', 'uk'), ('gov', 'uk'), ('ac', 'uk'),
                ('com', 'au'), ('net', 'au'), ('org', 'au'), ('co', 'nz')}
        last2 = (parts[-2], parts[-1])
        if last2 in slds and len(parts) >= 3:
            return '.'.join(parts[-3:])
        return '.'.join(parts[-2:])

    def get_domain_mapping(self, source_domain: str) -> Tuple[Optional[str], Optional[str]]:
        """Get domain/subdomain from mapping with normalization and fallbacks."""
        domain_map = self.config.get('domain_mapping', {}) or {}
        if not isinstance(domain_map, dict):
            domain_map = {}
        cand = self._normalize_domain(source_domain)
        candidates = [cand]
        base = self._base_domain(cand)
        if base and base not in candidates:
            candidates.append(base)
        if cand and ('www.' + cand) not in candidates:
            candidates.append('www.' + cand)
        if base and ('www.' + base) not in candidates:
            candidates.append('www.' + base)
        for key in candidates:
            if key in domain_map:
                m = domain_map.get(key) or {}
                return m.get('domain'), m.get('subdomain')
        for k, v in domain_map.items():
            nk = self._normalize_domain(k)
            if nk == cand or nk == base or self._base_domain(nk) == base:
                m = v or {}
                return m.get('domain'), m.get('subdomain')
        return None, None


# ============================================================================
# CLEANING UTILITIES (unchanged - keeping all your working logic)
# ============================================================================

class TextCleaner:
    """Text cleaning utilities"""

    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )

    @staticmethod
    def normalize_unicode(text: str) -> str:
        if not text:
            return ""
        import unicodedata
        text = unicodedata.normalize('NFKC', text)
        replacements = {
            '\u2018': "'", '\u2019': "'", '\u201A': ',', '\u201B': "'",
            '\u201C': '"', '\u201D': '"', '\u201E': '"',
            '\u2013': '-', '\u2014': '-', '\u2212': '-',
            '\u00A0': ' ', '\u2009': ' ', '\u202F': ' ', '\u200B': '',
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        text = ''.join(ch for ch in text if (ch == '\n' or ch == '\t' or (ch >= ' ')))
        return text

    @staticmethod
    def clean_html(
            html: str,
            xpath: Optional[str] = None,
            prune_xpath: List[str] = None,
            include_tables: bool = True,
            include_images: bool = True,
            include_links: bool = False,
            config: Any = None,
    ) -> str:
        if not html or not html.strip():
            return ""

        if config is None:
            config = use_config()
            config.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")

        if xpath:
            try:
                from lxml import html as lxml_html
                doc = lxml_html.fromstring(html)
                nodes = doc.xpath(xpath)
                if nodes:
                    html = ''.join(lxml_html.tostring(n, encoding='unicode') for n in nodes)
            except Exception as e:
                logging.debug(f"XPath selection failed: {e}")

        extracted = extract(
            html,
            config=config,
            include_tables=include_tables,
            include_images=include_images,
            include_links=include_links,
            prune_xpath=prune_xpath or [],
            favor_precision=True,
            include_comments=False,
        )

        return trafilatura.utils.sanitize(extracted) if extracted else ''

    @staticmethod
    def clean_title(title: str) -> str:
        if not title:
            return ""
        title = re.sub(r'&#?\w+;', ' ', title)
        title = ' '.join(title.split())
        return title.strip()

    @staticmethod
    def clean_emoji(text: str) -> str:
        return TextCleaner.EMOJI_PATTERN.sub('', text)

    @staticmethod
    def clean_whitespace(text: str) -> str:
        text = re.sub(r' +', ' ', text)
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        return text.strip()

    @staticmethod
    def anonymize_emails(text: str) -> str:
        def replace_email(match):
            email = match.group(0)
            parts = email.split('@')
            if len(parts) != 2:
                return email
            local, domain = parts
            domain_parts = domain.split('.')
            anonymized_local = 'x' * len(local)
            anonymized_domain = '.'.join('x' * len(part) for part in domain_parts)
            return f"{anonymized_local}@{anonymized_domain}"

        return TextCleaner.EMAIL_PATTERN.sub(replace_email, text)

    @staticmethod
    def clean_punctuation(text: str) -> str:
        text = re.sub(r'([!?.]){3,}', r'\1\1', text)
        return text

    @staticmethod
    def is_english(text: str, threshold: float = 0.7) -> bool:
        if not text or len(text) < 50:
            return True
        ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
        total_letters = sum(1 for c in text if c.isalpha())
        if total_letters == 0:
            return False
        ratio = ascii_letters / total_letters
        return ratio >= threshold


# ============================================================================
# HTML PREPROCESSING (unchanged)
# ============================================================================

PLACEHOLDER_IMG_PREFIX = "[[DYNACLEAN_IMG_"
PLACEHOLDER_TBL_PREFIX = "[[DYNACLEAN_TBL_"
PLACEHOLDER_SUFFIX = "]]"


def _latex_escape(text: str) -> str:
    if text is None:
        return ''
    replacements = {
        '\\': r'\\',
        '&': r'\&',
        '%': r'\%',
        '$': r'\$',
        '#': r'\#',
        '_': r'\_',
        '{': r'\{',
        '}': r'\}',
        '~': r'\textasciitilde{}',
        '^': r'\textasciicircum{}',
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    text = ' '.join(text.split())
    return text


def _html_table_to_latex(table_html: str) -> str:
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return table_html or ''

    try:
        soup = BeautifulSoup(table_html or '', 'lxml')
        table = soup.find('table') or soup
        rows = []
        for tr in table.find_all('tr'):
            cells = []
            for cell in tr.find_all(['th', 'td']):
                text = cell.get_text(separator=' ', strip=True)
                cells.append(_latex_escape(text))
            if cells:
                rows.append(cells)
        if not rows:
            return ''
        ncols = max(len(r) for r in rows)
        colspec = '|' + '|'.join(['l'] * ncols) + '|'
        lines = [f"\\begin{{tabular}}{{{colspec}}}", "\\hline"]
        for idx, r in enumerate(rows):
            if len(r) < ncols:
                r = r + [''] * (ncols - len(r))
            line = ' & '.join(r) + r" \\\\"
            lines.append(line)
            lines.append("\\hline")
        lines.append("\\end{tabular}")
        return "\n".join(lines)
    except Exception:
        return ''


def preprocess_html_for_media(html: str, base_url: str = None) -> tuple:
    if not html:
        return '', {}
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return html, {}

    from urllib.parse import urljoin

    def absolutize(u: str) -> str:
        if not u:
            return ''
        if base_url:
            try:
                return urljoin(base_url, u)
            except Exception:
                return u
        return u

    def is_placeholder(u: str) -> bool:
        if not u:
            return True
        ul = u.strip().lower()
        if ul.startswith('data:'):
            return True
        if any(tok in ul for tok in ['placeholder', 'blank', 'spacer', 'transparent']):
            return True
        if ul.endswith('.svg') or 'svg+xml' in ul:
            return True
        return False

    def parse_srcset(srcset_val: str) -> str:
        if not srcset_val:
            return ''
        best_url = ''
        best_w = -1.0
        for part in srcset_val.split(','):
            cand = part.strip()
            if not cand:
                continue
            pieces = cand.split()
            url = pieces[0]
            desc = pieces[1] if len(pieces) > 1 else ''
            w = 0.0
            try:
                if desc.endswith('w'):
                    w = float(desc[:-1])
                elif desc.endswith('x'):
                    w = float(desc[:-1]) * 1000.0
            except Exception:
                w = 0.0
            if w == 0.0:
                w = 1.0 if best_w < 0 else best_w + 1.0
            if w > best_w:
                best_w = w
                best_url = url
        return best_url

    soup = BeautifulSoup(html, 'lxml')
    mapping = {}

    for tbl in soup.find_all('table'):
        pid = str(uuid4()).replace('-', '')
        placeholder = f"{PLACEHOLDER_TBL_PREFIX}{pid}{PLACEHOLDER_SUFFIX}"
        latex = _html_table_to_latex(str(tbl))
        mapping[placeholder] = latex
        tbl.replace_with(placeholder)

    def resolve_image_src(img_tag) -> str:
        attr_order = [
            'data-full-url', 'data-large_image', 'data-orig-file', 'data-zoom-image',
            'data-pin-media', 'data-lazy-src', 'data-src', 'data-original', 'data-hi-res-src',
            'data-image', 'data-img', 'data-url', 'src'
        ]
        for a in attr_order:
            val = img_tag.get(a)
            if val and not is_placeholder(val):
                return absolutize(val)
        for a in ('data-srcset', 'data-lazy-srcset', 'srcset'):
            ssv = img_tag.get(a)
            if ssv:
                cand = parse_srcset(ssv)
                if cand and not is_placeholder(cand):
                    return absolutize(cand)
        parent = img_tag.parent
        if parent and parent.name == 'picture':
            sources = parent.find_all('source')
            for s in sources:
                ssv = s.get('srcset') or s.get('data-srcset')
                if ssv:
                    cand = parse_srcset(ssv)
                    if cand and not is_placeholder(cand):
                        return absolutize(cand)
        link = img_tag.find_parent('a')
        if link:
            href = link.get('href')
            if href and re.search(r'\.(?:jpe?g|png|webp|gif)(?:\?|#|$)', href, flags=re.I):
                return absolutize(href)
        val = img_tag.get('src')
        return absolutize(val) if val else ''

    for img in soup.find_all('img'):
        pid = str(uuid4()).replace('-', '')
        placeholder = f"{PLACEHOLDER_IMG_PREFIX}{pid}{PLACEHOLDER_SUFFIX}"
        src = resolve_image_src(img)
        if src and not is_placeholder(src):
            custom = f"[Image: {src}\\]"
            mapping[placeholder] = custom
            img.replace_with(placeholder)
        else:
            img.decompose()

    for level in range(2, 7):
        for h in soup.find_all(f'h{level}'):
            text = h.get_text(separator=' ', strip=True)
            if not text:
                h.decompose()
                continue
            pid = str(uuid4()).replace('-', '')
            ph = f"[[DYNACLEAN_HDR_{level}_{pid}]]"
            mapping[ph] = f"{text}\n"
            try:
                p = soup.new_tag('p')
                p.string = ph
                h.replace_with(p)
            except Exception:
                h.replace_with(ph)

    def _contains_placeholder(tag):
        try:
            return tag.find(string=lambda s: isinstance(s, str) and (
                        PLACEHOLDER_IMG_PREFIX in s or PLACEHOLDER_TBL_PREFIX in s or '[[DYNACLEAN_HDR_' in s)) is not None
        except Exception:
            return False

    for a in soup.find_all('a'):
        if _contains_placeholder(a):
            a.unwrap()
    for n in soup.find_all('noscript'):
        if _contains_placeholder(n):
            n.unwrap()
    for pic in soup.find_all(['picture', 'figure']):
        if _contains_placeholder(pic):
            pic.unwrap()

    return str(soup), mapping


def restore_placeholders(text: str, mapping: dict) -> str:
    if not text or not mapping:
        return text or ''
    for k, v in mapping.items():
        try:
            text = text.replace(k, v)
        except Exception:
            continue
    return text


# ============================================================================
# DOMAIN INFERENCE (unchanged)
# ============================================================================

class DomainInferencer:
    """Infer domain and subdomain from content"""

    DOMAIN_KEYWORDS = {
        'food': ['recipe', 'cooking', 'food', 'cuisine', 'meal', 'restaurant', 'chef'],
        'travel': ['travel', 'trip', 'vacation', 'tourism', 'destination', 'journey'],
        'technology': ['tech', 'software', 'hardware', 'computer', 'digital', 'coding'],
        'health': ['health', 'fitness', 'wellness', 'medical', 'exercise', 'nutrition'],
        'lifestyle': ['lifestyle', 'living', 'home', 'family', 'personal', 'daily'],
        'business': ['business', 'finance', 'money', 'investment', 'career', 'work'],
        'entertainment': ['entertainment', 'movie', 'music', 'game', 'fun', 'celebrity']
    }

    @staticmethod
    def infer_from_metadata(body_json: Dict, config_loader: ConfigLoader,
                            source_domain: str, url_hint: Optional[str] = None,
                            title_hint: Optional[str] = None, meta: Optional[Dict] = None) -> Tuple[
        Optional[str], Optional[str]]:
        mapped_domain, mapped_subdomain = config_loader.get_domain_mapping(source_domain or '')
        if mapped_domain and mapped_subdomain:
            return mapped_domain, mapped_subdomain

        dom_scores = Counter()
        sub_candidates: List[str] = []

        def score_terms(terms: List[str]):
            for term in terms:
                t = (term or '').strip().lower()
                if not t:
                    continue
                for dom, kws in DomainInferencer.DOMAIN_KEYWORDS.items():
                    if any(kw in t for kw in kws):
                        dom_scores[dom] += 1
                sub_candidates.append(t)

        body_json = body_json or {}
        meta = meta or {}

        meta_terms = []
        for key in ('categories_names', 'tags_names', 'sections', 'section', 'category'):
            val = meta.get(key)
            if isinstance(val, list):
                meta_terms.extend([str(x) for x in val])
            elif isinstance(val, str):
                meta_terms.append(val)
        categories = body_json.get('categories', [])
        tags = body_json.get('tags', [])
        if isinstance(categories, list) and categories and not all(isinstance(c, int) for c in categories):
            meta_terms.extend([str(c) for c in categories])
        if isinstance(tags, list) and tags and not all(isinstance(t, int) for t in tags):
            meta_terms.extend([str(t) for t in tags])
        if meta_terms:
            score_terms([str(x).lower() for x in meta_terms])

        class_list = body_json.get('class_list', [])
        if isinstance(class_list, list) and class_list:
            dom, sub = DomainInferencer._extract_from_classes(class_list)
            if sub:
                sub_candidates.append(sub.lower())
            if dom:
                dom_scores[dom] += 2

        if title_hint:
            score_terms(re.split(r'[^a-zA-Z]+', title_hint.lower()))

        url = (body_json.get('link') or url_hint or '').strip()
        if url:
            dom2, sub2 = DomainInferencer._infer_from_url(url)
            if sub2:
                sub_candidates.append(sub2.lower())
            if dom2:
                dom_scores[dom2] += 1

        domain = dom_scores.most_common(1)[0][0] if dom_scores else None
        chosen_sub = None
        if sub_candidates:
            if domain:
                for sc in sub_candidates:
                    mapped = DomainInferencer._map_subdomain_to_domain(sc)
                    if mapped == domain:
                        chosen_sub = sc
                        break
            if not chosen_sub:
                chosen_sub = sub_candidates[0]

        return domain, chosen_sub

    @staticmethod
    def _extract_from_classes(class_list: List[str]) -> Tuple[Optional[str], Optional[str]]:
        domain = None
        subdomain = None
        for cls in class_list:
            if cls.startswith('category-'):
                subdomain = cls.replace('category-', '').replace('-', ' ')
            elif cls.startswith('tag-'):
                tag = cls.replace('tag-', '').replace('-', ' ')
                if not subdomain:
                    subdomain = tag
        if subdomain:
            domain = DomainInferencer._map_subdomain_to_domain(subdomain)
        return domain, subdomain

    @staticmethod
    def _infer_from_terms(categories: List, tags: List) -> Tuple[Optional[str], Optional[str]]:
        all_terms = []
        if isinstance(categories, list):
            all_terms.extend([str(c).lower() for c in categories])
        if isinstance(tags, list):
            all_terms.extend([str(t).lower() for t in tags])
        if not all_terms:
            return None, None
        domain_scores = Counter()
        for term in all_terms:
            for domain, keywords in DomainInferencer.DOMAIN_KEYWORDS.items():
                if any(kw in term for kw in keywords):
                    domain_scores[domain] += 1
        if domain_scores:
            domain = domain_scores.most_common(1)[0][0]
            subdomain = all_terms[0] if all_terms else None
            return domain, subdomain
        return None, None

    @staticmethod
    def _infer_from_url(url: str) -> Tuple[Optional[str], Optional[str]]:
        skip_terms = {
            'archive', 'archives', 'category', 'categories', 'tag', 'tags', 'page', 'author', 'date',
            'feed', 'wp', 'json', 'blog', 'post', 'posts', 'news'
        }
        try:
            m = re.match(r'^https?://[^/]+(/[^?#]*)', url)
            path = m.group(1) if m else ''
            segs = [s for s in re.split(r'[/_-]+', path) if s]
            cand = []
            for s in segs:
                t = re.sub(r'[^a-zA-Z]', '', s).lower()
                if not t or t in skip_terms or len(t) < 3:
                    continue
                if t.isdigit():
                    continue
                cand.append(t)
            if not cand:
                return None, None
            scores = Counter()
            for s in cand:
                for dom, kws in DomainInferencer.DOMAIN_KEYWORDS.items():
                    if any(kw in s for kw in kws):
                        scores[(dom, s)] += 1
            if scores:
                (dom, sub), _ = scores.most_common(1)[0]
                return dom, sub
            sub = cand[0]
            dom = DomainInferencer._map_subdomain_to_domain(sub)
            if dom:
                return dom, sub
            return None, None
        except Exception:
            return None, None

    @staticmethod
    def _map_subdomain_to_domain(subdomain: str) -> Optional[str]:
        subdomain = subdomain.lower()
        for domain, keywords in DomainInferencer.DOMAIN_KEYWORDS.items():
            if any(kw in subdomain for kw in keywords):
                return domain
        return None


# ============================================================================
# FILTERING (unchanged)
# ============================================================================

class RecordFilter:
    """Filter records based on pre and post filter rules"""

    @staticmethod
    def apply_pre_filter(record: Dict, config: CleaningConfig) -> Tuple[bool, str]:
        pre_filter = config.pre_filter
        url = record.get('url', '')
        re_url_patterns = pre_filter.get('re_url', [])
        for pattern in re_url_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False, f"url_pattern:{pattern}"
        return True, ""

    @staticmethod
    def check_body_length(text: str, config: CleaningConfig) -> Tuple[bool, str]:
        min_length = config.pre_filter.get('body_length', 200)
        if len(text) < min_length:
            return False, f"body_too_short:{len(text)}<{min_length}"
        return True, ""

    @staticmethod
    def apply_post_filter(title: str, cleaned_text: str, domain: str,
                          subdomain: str, config: CleaningConfig) -> Tuple[bool, str]:
        post_filter = config.post_filter
        for pattern in post_filter.get('re_cleaned_text', []):
            if re.search(pattern, cleaned_text, re.IGNORECASE):
                return False, f"text_pattern:{pattern}"
        for pattern in post_filter.get('re_title', []):
            if re.search(pattern, title, re.IGNORECASE):
                return False, f"title_pattern:{pattern}"
        for term in post_filter.get('domain_containing', []):
            if term.lower() in domain.lower():
                return False, f"domain_contains:{term}"
        for term in post_filter.get('subdomain_containing', []):
            if term.lower() in subdomain.lower():
                return False, f"subdomain_contains:{term}"
        return True, ""


# ============================================================================
# RECORD PROCESSOR (unchanged)
# ============================================================================

class RecordProcessor:
    """Process individual records"""

    def __init__(self, config_loader: ConfigLoader, sitekey: str):
        self.config_loader = config_loader
        self.config = config_loader.get_site_config(sitekey)
        self.cleaner = TextCleaner()
        try:
            self.trafilatura_config = use_config()
            self.trafilatura_config.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
        except Exception:
            self.trafilatura_config = None

    def process_wordpress(self, record: Dict) -> Optional[Dict]:
        try:
            should_process, reason = RecordFilter.apply_pre_filter(record, self.config)
            if not should_process:
                return {'status': 'filtered_pre', 'reason': reason}

            body_raw = record.get('body', '{}')
            if isinstance(body_raw, dict):
                body = body_raw
            elif isinstance(body_raw, str) and body_raw.strip():
                try:
                    body = json.loads(body_raw)
                except Exception as e:
                    return {'status': 'error', 'reason': f'json_parse_error:{e}'}
            else:
                body = {}

            url = record.get('url', '')
            record_id = record.get('id', str(uuid4()))
            meta = record.get('meta') or {}
            source_domain = meta.get('site', '') or meta.get('source', '') or ''
            if (not source_domain) and url:
                try:
                    source_domain = ConfigLoader._normalize_domain(url)
                except Exception:
                    source_domain = ''

            title_raw = (body or {}).get('title', {})
            if isinstance(title_raw, dict):
                title = title_raw.get('rendered', '') or ''
            elif title_raw is None:
                title = ''
            else:
                title = str(title_raw)

            content_raw = (body or {}).get('content', {})
            if isinstance(content_raw, dict):
                body_html = content_raw.get('rendered', '') or ''
            elif content_raw is None:
                body_html = ''
            else:
                body_html = str(content_raw)

            cleaned_title = self._apply_cleaning_pipeline(title, is_title=True)

            clean_args = self.config.clean.get('args', {})
            xpath = clean_args.get('body_xpath')
            noises = clean_args.get('noises', [])

            html_with_placeholders, ph_map = preprocess_html_for_media(body_html, base_url=url)

            formating = clean_args.get('formating', {})
            include_links = bool(formating.get('retain_links', False))

            extracted_body = self.cleaner.clean_html(
                html_with_placeholders,
                xpath,
                noises,
                include_tables=False,
                include_images=False,
                include_links=include_links,
                config=self.trafilatura_config,
            )

            cleaned_body = restore_placeholders(extracted_body, ph_map)

            if not cleaned_body:
                return {'status': 'filtered_pre', 'reason': 'empty_after_extraction'}

            should_process, reason = RecordFilter.check_body_length(cleaned_body, self.config)
            if not should_process:
                return {'status': 'filtered_pre', 'reason': reason}

            cleaned_body = self._apply_cleaning_pipeline(cleaned_body, is_title=False)

            if 'english_only' in self.config.clean.get('enabled', []):
                if not self.cleaner.is_english(cleaned_body):
                    return {'status': 'filtered_pre', 'reason': 'not_english'}

            domain = self.config.domain_override
            subdomain = self.config.subdomain_override

            if not domain or not subdomain:
                inferred_domain, inferred_subdomain = DomainInferencer.infer_from_metadata(
                    body, self.config_loader, source_domain, url_hint=url, title_hint=cleaned_title, meta=meta
                )
                domain = domain or inferred_domain or self.config.domain_fallback
                subdomain = subdomain or inferred_subdomain or self.config.subdomain_fallback

            should_process, reason = RecordFilter.apply_post_filter(
                cleaned_title, cleaned_body, domain, subdomain, self.config
            )
            if not should_process:
                return {'status': 'filtered_post', 'reason': reason}

            output = {
                'id': record_id,
                'text': f"{cleaned_title}\n{cleaned_body}",
                'meta': {
                    'data_info': {
                        'lang': 'en',
                        'url': url,
                        'source': source_domain,
                        'type': 'website content',
                        'processing_date': datetime.now().isoformat(),
                        'delivery_version': self.config.delivery_version,
                        'title': cleaned_title
                    },
                    'content_info': {
                        'domain': domain,
                        'subdomain': subdomain
                    }
                }
            }

            return {'status': 'success', 'data': output}

        except Exception as e:
            logging.error(f"Processing error: {e}", exc_info=True)
            return {'status': 'error', 'reason': f'exception:{str(e)}'}

    def _apply_cleaning_pipeline(self, text: str, is_title: bool = False) -> str:
        enabled = self.config.clean.get('enabled', [])

        if is_title:
            if 'clean_title' in enabled:
                text = self.cleaner.clean_title(text)

        if 'normalize_unicode' in enabled:
            text = self.cleaner.normalize_unicode(text)
        if 'clean_emoji' in enabled:
            text = self.cleaner.clean_emoji(text)
        if 'anonymization' in enabled:
            text = self.cleaner.anonymize_emails(text)
        if 'clean_punctuation' in enabled:
            text = self.cleaner.clean_punctuation(text)
        if 'clean_whitespace' in enabled:
            text = self.cleaner.clean_whitespace(text)

        return text

# ============================================================================
# WORKER CACHE (FOR PERFORMANCE)
# ============================================================================
PROCESSOR_CACHE: Dict[str, RecordProcessor] = {}

# ============================================================================
# OPTIMIZED BATCH PROCESSOR - THE SPEED SECRET
# ============================================================================

def process_batch_consumer(input_queue: Queue, output_queue: Queue, seen_urls: 'Manager.dict'):
    """
    The main loop for a single worker process.
    Pulls from input_queue, processes, pushes to output_queue.
    """
    try:
        while True:
            # Get a job
            item = input_queue.get()

            # Poison pill check
            if item is None:
                break

            batch, config_path, sitekey = item

            # Process the batch (this is the existing function)
            successes, duplicates, failures = process_batch_worker((batch, config_path, sitekey, seen_urls))

            # Put results onto the output queue, tagged with their sitekey
            for res in successes:
                output_queue.put((res, sitekey))
            for res in duplicates:
                output_queue.put((res, sitekey))
            for res in failures:
                output_queue.put((res, sitekey))

    except Exception as e:
        logging.error(f"Process worker consumer failed: {e}")

def process_batch_worker(batch_data: Tuple) -> Tuple[List[Dict], List[Dict], List[Dict]]:
    """
    Process a batch of raw lines in parallel.
    - Decodes JSON here
    - Caches processor for speed
    - PERFORMS DEDUPLICATION HERE
    """
    line_batch, config_path, sitekey, seen_urls = batch_data

    # Use module-level cache to store processors
    global PROCESSOR_CACHE
    if sitekey not in PROCESSOR_CACHE:
        try:
            config_loader = ConfigLoader(config_path)
            PROCESSOR_CACHE[sitekey] = RecordProcessor(config_loader, sitekey)
        except Exception as e:
            # Failed to create processor, fail all items in batch
            fail_reason = {'status': 'error', 'reason': f'processor_init_fail:{e}'}
            return ([], [], [fail_reason] * len(line_batch))

    processor = PROCESSOR_CACHE[sitekey]

    successes = []
    duplicates = []
    failures = []

    for line in line_batch:
        try:
            # 1. DECODE JSON
            record = json.loads(line)
        except Exception as e:
            failures.append({'status': 'error', 'reason': f'json_parse_error:{e}'})
            continue

        try:
            # 2. Process the record
            result = processor.process_wordpress(record)
        except Exception as e:
            failures.append({'status': 'error', 'reason': f'processing_exception:{e}'})
            continue

        # 3. CLASSIFY AND DEDUPE RESULT
        status = result.get('status', 'error')

        if status == 'success':
            url = result.get('data', {}).get('meta', {}).get('data_info', {}).get('url')
            if url:
                # Check and set atomic-like operation in shared dict
                if url in seen_urls:
                    result['status'] = 'duplicate'
                    result['reason'] = f'duplicate_url:{url}'
                    duplicates.append(result)
                else:
                    seen_urls[url] = 1  # Mark as seen
                    successes.append(result)
            else:
                successes.append(result)  # No URL, cannot dedupe
        else:
            failures.append(result)  # 'error', 'filtered_pre', 'filtered_post'

    return (successes, duplicates, failures)


def global_file_reader(input_files: List[Path], config_path: str, batch_size: int, input_queue: Queue):
    """
    A single, dedicated thread to read all files and feed the input queue.
    """
    try:
        for input_file in input_files:
            sitekey = input_file.stem
            batch = []

            try:
                with open(input_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line_stripped = line.strip()
                        if not line_stripped:
                            continue

                        batch.append(line_stripped)

                        if len(batch) >= batch_size:
                            input_queue.put((batch, config_path, sitekey))
                            batch = []

                    # Put remaining records for this file
                    if batch:
                        input_queue.put((batch, config_path, sitekey))
            except Exception as e:
                logging.error(f"Error reading file {input_file.name}: {e}")

    except Exception as e:
        logging.error(f"Global file reader thread failed: {e}")
    finally:
        # Signal that the reader is done
        logging.info("File reader has finished.")

def async_file_reader(filepath: Path, batch_size: int, input_queue: Queue):
    """Asynchronously read file and feed batches of RAW LINES to queue"""
    try:
        batch = []
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line_stripped = line.strip()
                if not line_stripped:
                    continue

                # Queue the raw line, not the decoded JSON
                batch.append(line_stripped)

                if len(batch) >= batch_size:
                    input_queue.put(batch)
                    batch = []

            # Put remaining records
            if batch:
                input_queue.put(batch)

        # Signal completion
        input_queue.put(None)
    except Exception as e:
        logging.error(f"File reader error: {e}")
        input_queue.put(None)


def global_file_writer(output_queue: Queue, output_dir: Path, failed_dir: Path) -> Dict:
    """
    Asynchronously write results from all workers to the correct files.
    This is now the main progress tracker and stats accumulator.
    """
    open_files = {}
    stats = {
        'total': 0, 'success': 0, 'failed': 0,
        'filtered_pre': 0, 'filtered_post': 0, 'duplicates': 0
    }

    pbar = None
    if tqdm:
        # No total, just a running counter
        pbar = tqdm(desc="Processing records", unit="rec", dynamic_ncols=True, leave=True)

    try:
        while True:
            item = output_queue.get()

            if item is None:  # Poison pill
                break

            result, sitekey = item

            if pbar is not None:
                pbar.update(1)

            # Update stats
            stats['total'] += 1
            status = result.get('status', 'error')

            if status == 'success':
                stats['success'] += 1
            elif status == 'duplicate':
                stats['duplicates'] += 1
            elif status == 'filtered_pre':
                stats['filtered_pre'] += 1
            elif status == 'filtered_post':
                stats['filtered_post'] += 1
            else:  # Catches 'error'
                stats['failed'] += 1

            # --- File writing logic ---
            is_success = (status == 'success')
            target_dir = output_dir if is_success else failed_dir
            suffix = "_cleaned" if is_success else "_failed"
            file_key = f"{sitekey}{suffix}"

            try:
                if file_key not in open_files:
                    target_file = target_dir / f"{sitekey}{suffix}.jsonl"
                    open_files[file_key] = open(target_file, 'w', encoding='utf-8')

                f_handle = open_files[file_key]

                if is_success:
                    f_handle.write(json.dumps(result['data'], ensure_ascii=False) + '\n')
                else:
                    f_handle.write(json.dumps({
                        'reason': result.get('reason', 'unknown'),
                        'status': status,
                    }, ensure_ascii=False) + '\n')

            except Exception as e:
                logging.error(f"File writer error for site {sitekey}: {e}")

    except Exception as e:
        logging.error(f"Global file writer thread failed: {e}")
    finally:
        # Close all open files
        for f in open_files.values():
            f.close()
        if pbar is not None:
            pbar.close()

    return stats


# ============================================================================
# MAIN PIPELINE - SEQUENTIAL FILE PROCESSING
# ============================================================================
class DataCleaningPipeline:
    """Main pipeline - processes files one at a time with ALL cores"""

    def __init__(self, args):
        self.args = args
        self.setup_logging()

    def setup_logging(self):
        """Minimal logging setup - only errors to console"""
        log_file = Path(self.args.log_dir) / f"cleaning_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.INFO)  # Set to INFO
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.ERROR)  # Only errors to console

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        root = logging.getLogger()
        root.setLevel(logging.INFO)  # Set to INFO
        root.handlers.clear()
        root.addHandler(file_handler)
        root.addHandler(stream_handler)

        logging.getLogger('trafilatura').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

    def _start_writer_thread(self, output_queue, output_dir, failed_dir) -> Tuple[Thread, Queue]:
        """Helper to start the writer thread and give it a queue to return stats."""
        stats_return_queue = Queue()
        thread = Thread(
            target=lambda: stats_return_queue.put(
                global_file_writer(output_queue, output_dir, failed_dir)
            ),
            daemon=True
        )
        thread.start()
        return thread, stats_return_queue

    def run(self):
        """Execute pipeline - ONE shared pool, THREE decoupled stages."""
        input_dir = Path(self.args.input_dir)
        output_dir = Path(self.args.output_dir)
        failed_dir = Path(self.args.failed_dir)

        output_dir.mkdir(parents=True, exist_ok=True)
        failed_dir.mkdir(parents=True, exist_ok=True)

        input_files = sorted(input_dir.glob('*.jsonl'))

        if not input_files:
            logging.error(f"No .jsonl files found in {input_dir}")
            print(f"ERROR: No .jsonl files found in {input_dir}")
            return

        print(f"\n{'=' * 70}")
        print(f"DECOUPLED PIPELINE: {len(input_files)} files | {self.args.workers} cores")
        print(f"Starting all threads and worker processes...")
        print(f"{'=' * 70}\n")

        start_time = time.time()
        total_stats = {}

        # Use Manager to create queues and dict that can be shared by all processes
        with Manager() as manager:

            # 1. Create shared (and deep) queues
            queue_depth = max(200, self.args.workers * 10)  # At least 200
            input_queue = manager.Queue(maxsize=queue_depth)
            output_queue = manager.Queue(maxsize=queue_depth)

            # 2. Create shared deduplication dictionary
            self.seen_urls = manager.dict()

            # 3. Start the WRITER thread
            writer_thread, stats_queue = self._start_writer_thread(
                output_queue, output_dir, failed_dir
            )

            # 4. Start the READER thread
            reader_thread = Thread(
                target=global_file_reader,
                args=(input_files, self.args.config, self.args.batch_size, input_queue),
                daemon=True
            )
            reader_thread.start()

            # 5. Start the PROCESS Pool
            try:
                with ProcessPoolExecutor(max_workers=self.args.workers) as executor:
                    futures = [
                        executor.submit(
                            process_batch_consumer,
                            input_queue,
                            output_queue,
                            self.seen_urls
                        )
                        for _ in range(self.args.workers)
                    ]

                    # Wait for the reader thread to finish loading all files
                    reader_thread.join()
                    logging.info("Reader thread joined. All files are queued.")

                    # Now that the reader is done, send poison pills to the workers
                    for _ in range(self.args.workers):
                        input_queue.put(None)

                    # Wait for all worker processes to finish
                    for fut in as_completed(futures):
                        fut.result()  # Check for exceptions
                    logging.info("All worker processes have finished.")

                    # Now that workers are done, send a poison pill to the writer
                    output_queue.put(None)

                    # Wait for the writer to finish and get the final stats
                    writer_thread.join()
                    total_stats = stats_queue.get()

            except KeyboardInterrupt:
                print("\nInterrupted! Shutting down...")
            except Exception as e:
                logging.error(f"Main pipeline failed: {e}", exc_info=True)

        total_time = time.time() - start_time

        # Final summary
        if total_stats:
            self.print_summary(total_stats, total_time)
        else:
            print("Pipeline finished, but no stats were collected.")

    def print_summary(self, stats: Dict, elapsed: float):
        """Print final summary"""
        print(f"\n{'=' * 70}")
        print("FINAL SUMMARY")
        print(f"{'=' * 70}")

        # Ensure all keys exist
        total = stats.get('total', 0)
        success = stats.get('success', 0)
        duplicates = stats.get('duplicates', 0)
        filtered_pre = stats.get('filtered_pre', 0)
        filtered_post = stats.get('filtered_post', 0)
        failed = stats.get('failed', 0)

        print(f"Total Records Processed: {total:,}")
        print(f"Successfully Cleaned:    {success:,}")
        print(f"Duplicates (URL):        {duplicates:,}")
        print(f"Pre-filtered:            {filtered_pre:,}")
        print(f"Post-filtered:           {filtered_post:,}")
        print(f"Failed (Errors):         {failed:,}")

        if total > 0:
            # Calculate success rate based on total *non-duplicate* records
            valid_records = total - duplicates
            success_rate = (success / valid_records * 100) if valid_records > 0 else 0
            speed = total / elapsed if elapsed > 0 else 0
            print(f"\nSuccess Rate (of non-dups): {success_rate:.2f}%")
            print(f"Total Time:               {elapsed:.1f}s")
            print(f"Average Speed:            {speed:.0f} records/second")

        print(f"{'=' * 70}\n")

# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='OPTIMIZED High-Performance Data Cleaning Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('-i', '--input-dir', type=str, default='./input',
                        help='Input directory (default: ./input)')
    parser.add_argument('-o', '--output-dir', type=str, default='./output',
                        help='Output directory (default: ./output)')
    parser.add_argument('-f', '--failed-dir', type=str, default='./failed',
                        help='Failed records directory (default: ./failed)')
    parser.add_argument('-c', '--config', type=str, default='cleaning_map.yaml',
                        help='Config YAML file (default: cleaning_map.yaml)')
    parser.add_argument('-w', '--workers', type=int, default=cpu_count(),
                        help=f'Worker processes (default: {cpu_count()})')
    parser.add_argument('-b', '--batch-size', type=int, default=100,
                        help='Records per batch (default: 100, larger=more RAM, more speed)')
    parser.add_argument('-l', '--log-dir', type=str, default='./logs',
                        help='Log directory (default: ./logs)')

    args = parser.parse_args()

    pipeline = DataCleaningPipeline(args)
    pipeline.run()


if __name__ == '__main__':
    main()