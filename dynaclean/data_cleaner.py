#!/usr/bin/env python3
"""
High-Performance Data Cleaning Pipeline
Supports multiple data shapes with modular architecture
"""

import json
import re
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from multiprocessing import Manager, cpu_count
import sys
import os
import time

import trafilatura.utils
import yaml
from uuid import uuid4
from collections import Counter

# Optional progress bars
try:
    from tqdm.auto import tqdm
except Exception:
    tqdm = None

try:
    from trafilatura import extract, extract_metadata
    from trafilatura.settings import use_config
    from bs4 import BeautifulSoup
except ImportError:
    print("ERROR: Missing required packages. Install with:")
    print("pip install trafilatura beautifulsoup4 lxml pyyaml")
    sys.exit(1)


# ============================================================================
# DATA CLASSES
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
# CONFIGURATION LOADER
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

        # Get template config
        clean_section = site_config.get('clean') or {}
        if not isinstance(clean_section, dict):
            clean_section = {}
        template_name = clean_section.get('type', 'template_wordpress')
        template_root = self.config if isinstance(self.config, dict) else {}
        template = template_root.get(template_name) or template_root.get('template_wordpress') or {}
        if not isinstance(template, dict):
            template = {}

        # Merge site config with template (site overrides template); ignore None values
        merged = self._merge_configs(template, site_config)

        # Ensure sub-sections are dicts
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
            # Skip None overrides entirely to avoid clobbering dicts with None
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
        # Remove scheme
        d = re.sub(r'^https?://', '', d)
        # Remove path and query
        d = d.split('/')[0]
        # Remove port
        d = d.split(':')[0]
        # Strip leading www.
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
        # Handle common SLDs like co.uk, com.au, org.uk, gov.uk, ac.uk, co.nz
        slds = {('co', 'uk'), ('org', 'uk'), ('gov', 'uk'), ('ac', 'uk'),
                ('com', 'au'), ('net', 'au'), ('org', 'au'), ('co', 'nz')}
        last2 = (parts[-2], parts[-1])
        last3 = (parts[-3], parts[-2])
        if last2 in slds and len(parts) >= 3:
            return '.'.join(parts[-3:])
        if last3 in slds and len(parts) >= 4:
            return '.'.join(parts[-4:])
        return '.'.join(parts[-2:])

    def get_domain_mapping(self, source_domain: str) -> Tuple[Optional[str], Optional[str]]:
        """Get domain/subdomain from mapping with normalization and fallbacks."""
        domain_map = self.config.get('domain_mapping', {}) or {}
        if not isinstance(domain_map, dict):
            domain_map = {}
        cand = self._normalize_domain(source_domain)
        candidates = [cand]
        # Also try base domain and original key
        base = self._base_domain(cand)
        if base and base not in candidates:
            candidates.append(base)
        # Try with and without www
        if cand and ('www.' + cand) not in candidates:
            candidates.append('www.' + cand)
        if base and ('www.' + base) not in candidates:
            candidates.append('www.' + base)
        for key in candidates:
            if key in domain_map:
                m = domain_map.get(key) or {}
                return m.get('domain'), m.get('subdomain')
        # Final attempt: iterate keys and compare normalized/base
        for k, v in domain_map.items():
            nk = self._normalize_domain(k)
            if nk == cand or nk == base or self._base_domain(nk) == base:
                m = v or {}
                return m.get('domain'), m.get('subdomain')
        return None, None


# ============================================================================
# CLEANING UTILITIES
# ============================================================================

class TextCleaner:
    """Text cleaning utilities"""

    EMAIL_PATTERN = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')
    EMOJI_PATTERN = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # emoticons
        "\U0001F300-\U0001F5FF"  # symbols & pictographs
        "\U0001F680-\U0001F6FF"  # transport & map symbols
        "\U0001F1E0-\U0001F1FF"  # flags
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )

    @staticmethod
    def normalize_unicode(text: str) -> str:
        """Normalize unicode: NFKC normalization, map smart quotes/dashes to ASCII,
        remove control characters except newlines and tabs.
        """
        if not text:
            return ""
        import unicodedata
        # Normalize compatibility characters
        text = unicodedata.normalize('NFKC', text)
        # Map common punctuation to ASCII
        replacements = {
            '\u2018': "'", '\u2019': "'", '\u201A': ',', '\u201B': "'",
            '\u201C': '"', '\u201D': '"', '\u201E': '"',
            '\u2013': '-', '\u2014': '-', '\u2212': '-',
            '\u00A0': ' ', '\u2009': ' ', '\u202F': ' ', '\u200B': '',
        }
        for k, v in replacements.items():
            text = text.replace(k, v)
        # Remove other control characters
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
        """Extract clean text from HTML using trafilatura.
        - Supports true XPath pre-selection (not CSS).
        - Respects include_tables/images/links flags from config.
        """
        if not html or not html.strip():
            return ""

        # Reuse provided config for performance if available
        if config is None:
            config = use_config()
            config.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")

        # Apply XPath selector if specified (use lxml)
        if xpath:
            try:
                from lxml import html as lxml_html
                doc = lxml_html.fromstring(html)
                nodes = doc.xpath(xpath)
                if nodes:
                    html = ''.join(lxml_html.tostring(n, encoding='unicode') for n in nodes)
            except Exception as e:
                logging.debug(f"XPath selection failed: {e}")

        # Extract with trafilatura
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
        """Clean title text"""
        if not title:
            return ""
        # Remove HTML entities
        title = re.sub(r'&#?\w+;', ' ', title)
        # Remove extra whitespace
        title = ' '.join(title.split())
        return title.strip()

    @staticmethod
    def clean_emoji(text: str) -> str:
        """Remove emojis from text"""
        return TextCleaner.EMOJI_PATTERN.sub('', text)

    @staticmethod
    def clean_whitespace(text: str) -> str:
        """Normalize whitespace"""
        # Replace multiple spaces with single space
        text = re.sub(r' +', ' ', text)
        # Replace multiple newlines with double newline
        text = re.sub(r'\n\s*\n\s*\n+', '\n\n', text)
        return text.strip()

    @staticmethod
    def anonymize_emails(text: str) -> str:
        """Replace emails with xxx@xxxxx.xxx"""

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
        """Clean excessive punctuation"""
        # Remove multiple punctuation marks
        text = re.sub(r'([!?.]){3,}', r'\1\1', text)
        return text

    @staticmethod
    def is_english(text: str, threshold: float = 0.7) -> bool:
        """Simple heuristic to check if text is mostly English"""
        if not text or len(text) < 50:
            return True  # Too short to determine

        # Count ASCII letters vs total characters
        ascii_letters = sum(1 for c in text if c.isascii() and c.isalpha())
        total_letters = sum(1 for c in text if c.isalpha())

        if total_letters == 0:
            return False

        ratio = ascii_letters / total_letters
        return ratio >= threshold


# ============================================================================
# CUSTOM HTML MEDIA/TABLE PREPROCESSING
# ==========================================================================

PLACEHOLDER_IMG_PREFIX = "[[DYNACLEAN_IMG_"
PLACEHOLDER_TBL_PREFIX = "[[DYNACLEAN_TBL_"
PLACEHOLDER_SUFFIX = "]]"


def _latex_escape(text: str) -> str:
    """Escape LaTeX special characters in cell text."""
    if text is None:
        return ''
    # Basic escapes
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
    # Collapse whitespace inside cells
    text = ' '.join(text.split())
    return text


def _html_table_to_latex(table_html: str) -> str:
    """Convert a simple HTML <table> to a LaTeX tabular environment.
    Handles <th>/<td>, multiple rows, and basic text. Complex nested tables are flattened.
    """
    try:
        from bs4 import BeautifulSoup
    except Exception:
        return table_html or ''

    try:
        soup = BeautifulSoup(table_html or '', 'lxml')
        table = soup.find('table') or soup
        # Determine rows
        rows = []
        for tr in table.find_all('tr'):
            cells = []
            # Prefer th for header row else td
            for cell in tr.find_all(['th', 'td']):
                # Get text content, fallback to stripped strings
                text = cell.get_text(separator=' ', strip=True)
                cells.append(_latex_escape(text))
            if cells:
                rows.append(cells)
        if not rows:
            return ''
        # Determine column count as max length
        ncols = max(len(r) for r in rows)
        colspec = '|' + '|'.join(['l'] * ncols) + '|'
        lines = [f"\\begin{{tabular}}{{{colspec}}}", "\\hline"]
        for idx, r in enumerate(rows):
            # pad missing cells
            if len(r) < ncols:
                r = r + [''] * (ncols - len(r))
            line = ' & '.join(r) + r" \\\\"  # end of row
            lines.append(line)
            lines.append("\\hline")
        lines.append("\\end{tabular}")
        return "\n".join(lines)
    except Exception:
        return ''


def _apply_pre_html_regex(html: str, pre_html_cfg: dict) -> str:
    """Apply pre-HTML regex cleaning to catch common noise at the beginning and end.
    pre_html_cfg: {
        'strip_begin_regex': [ ... ],
        'strip_end_regex': [ ... ],
        'strip_any_regex': [ ... ]
    }
    """
    if not html:
        return ''
    pre_html_cfg = pre_html_cfg or {}
    txt = html
    # Strip patterns anywhere
    for pat in pre_html_cfg.get('strip_any_regex', []) or []:
        try:
            txt = re.sub(pat, ' ', txt, flags=re.IGNORECASE | re.DOTALL)
        except re.error:
            pass
    # Strip from beginning
    for pat in pre_html_cfg.get('strip_begin_regex', []) or []:
        try:
            txt = re.sub(rf'^(?:\s|<!--.*?-->|<[^>]+>)*(?:{pat})+', ' ', txt, flags=re.IGNORECASE | re.DOTALL)
        except re.error:
            pass
    # Strip from end
    for pat in pre_html_cfg.get('strip_end_regex', []) or []:
        try:
            txt = re.sub(rf'(?:{pat})+(?:\s|<!--.*?-->|<[^>]+>)*$', ' ', txt, flags=re.IGNORECASE | re.DOTALL)
        except re.error:
            pass
    return txt


def preprocess_html_for_media(html: str, base_url: str = None) -> tuple:
    r"""Find <img>, <table>, and subheading elements and replace them with stable placeholders.
    Returns (html_with_placeholders, mapping_dict).
    mapping_dict maps placeholder text to final custom replacement text.
    - Images -> "[Image: {src}\]" (with trailing backslash)
    - Tables -> LaTeX tabular string
    - Headings (h2–h6) -> Markdown equivalents (##, ###, ####, ...)
    """
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
                    # Treat pixel density multiplier approx as width priority
                    w = float(desc[:-1]) * 1000.0
            except Exception:
                w = 0.0
            if w == 0.0:
                # Favor last candidate when no descriptor
                w = 1.0 if best_w < 0 else best_w + 1.0
            if w > best_w:
                best_w = w
                best_url = url
        return best_url

    soup = BeautifulSoup(html, 'lxml')
    mapping = {}

    # Process tables first to preserve structure placement
    for tbl in soup.find_all('table'):
        pid = str(uuid4()).replace('-', '')
        placeholder = f"{PLACEHOLDER_TBL_PREFIX}{pid}{PLACEHOLDER_SUFFIX}"
        latex = _html_table_to_latex(str(tbl))
        mapping[placeholder] = latex
        tbl.replace_with(placeholder)

    # Resolve best image URL with multiple fallbacks
    def resolve_image_src(img_tag) -> str:
        # 1) Attribute priority list
        attr_order = [
            'data-full-url', 'data-large_image', 'data-orig-file', 'data-zoom-image',
            'data-pin-media', 'data-lazy-src', 'data-src', 'data-original', 'data-hi-res-src',
            'data-image', 'data-img', 'data-url', 'src'
        ]
        for a in attr_order:
            val = img_tag.get(a)
            if val and not is_placeholder(val):
                return absolutize(val)
        # 2) srcset attributes (prefer largest)
        for a in ('data-srcset', 'data-lazy-srcset', 'srcset'):
            ssv = img_tag.get(a)
            if ssv:
                cand = parse_srcset(ssv)
                if cand and not is_placeholder(cand):
                    return absolutize(cand)
        # 3) picture/source siblings
        parent = img_tag.parent
        if parent and parent.name == 'picture':
            sources = parent.find_all('source')
            for s in sources:
                ssv = s.get('srcset') or s.get('data-srcset')
                if ssv:
                    cand = parse_srcset(ssv)
                    if cand and not is_placeholder(cand):
                        return absolutize(cand)
        # 4) link wrapper
        link = img_tag.find_parent('a')
        if link:
            href = link.get('href')
            if href and re.search(r'\.(?:jpe?g|png|webp|gif)(?:\?|#|$)', href, flags=re.I):
                return absolutize(href)
        # 5) last resort: original src even if placeholder
        val = img_tag.get('src')
        return absolutize(val) if val else ''

    # Process images
    for img in soup.find_all('img'):
        pid = str(uuid4()).replace('-', '')
        placeholder = f"{PLACEHOLDER_IMG_PREFIX}{pid}{PLACEHOLDER_SUFFIX}"
        src = resolve_image_src(img)
        if src and not is_placeholder(src):
            custom = f"[Image: {src}\\]"
            mapping[placeholder] = custom
            img.replace_with(placeholder)
        else:
            # remove image with no usable src
            img.decompose()

    # Preserve subheadings h2–h6 as plain text (single newline), no markdown
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

    # Unwrap wrappers that can cause placeholders to be dropped by trafilatura
    def _contains_placeholder(tag):
        try:
            return tag.find(string=lambda s: isinstance(s, str) and (PLACEHOLDER_IMG_PREFIX in s or PLACEHOLDER_TBL_PREFIX in s or '[[DYNACLEAN_HDR_' in s)) is not None
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
    """Replace placeholders in text with their mapped custom strings."""
    if not text or not mapping:
        return text or ''
    # Replace in deterministic order: images first, then tables, though order shouldn't matter
    for k, v in mapping.items():
        try:
            text = text.replace(k, v)
        except Exception:
            continue
    return text


# ============================================================================
# DOMAIN/SUBDOMAIN INFERENCE
# ============================================================================

class DomainInferencer:
    """Infer domain and subdomain from content"""

    # Common domain keywords
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
                            title_hint: Optional[str] = None, meta: Optional[Dict] = None) -> Tuple[Optional[str], Optional[str]]:
        """
        Infer domain/subdomain with priority:
        1. Config domain_mapping (normalized and base domain aware)
        2. Meta fields (categories/tags sections if present in meta/body)
        3. Class list extraction (category-*/tag-*)
        4. Title keyword inference
        5. URL path inference (multiple segments, ignore stopwords)
        6. Fallback: None (caller should apply config fallbacks)
        """
        # 1) Check domain mapping first (handles subdomains/variants)
        mapped_domain, mapped_subdomain = config_loader.get_domain_mapping(source_domain or '')
        if mapped_domain and mapped_subdomain:
            return mapped_domain, mapped_subdomain

        # Prepare candidate buckets
        dom_scores = Counter()
        sub_candidates: List[str] = []

        # Helper: score terms
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

        # 2) Meta/body categories/tags
        # Try common meta keys
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

        # 3) Class list extraction
        class_list = body_json.get('class_list', [])
        if isinstance(class_list, list) and class_list:
            dom, sub = DomainInferencer._extract_from_classes(class_list)
            if sub:
                sub_candidates.append(sub.lower())
            if dom:
                dom_scores[dom] += 2  # weight class-derived domain higher

        # 4) Title keyword inference
        if title_hint:
            score_terms(re.split(r'[^a-zA-Z]+', title_hint.lower()))

        # 5) URL inference using multiple path segments
        url = (body_json.get('link') or url_hint or '').strip()
        if url:
            dom2, sub2 = DomainInferencer._infer_from_url(url)
            if sub2:
                sub_candidates.append(sub2.lower())
            if dom2:
                dom_scores[dom2] += 1

        # Decide domain
        domain = dom_scores.most_common(1)[0][0] if dom_scores else None
        # Decide subdomain: pick the first candidate that maps to the chosen domain if possible
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
        """Extract domain/subdomain from class list"""
        domain = None
        subdomain = None

        for cls in class_list:
            # Look for category-xxx or tag-xxx
            if cls.startswith('category-'):
                subdomain = cls.replace('category-', '').replace('-', ' ')
            elif cls.startswith('tag-'):
                tag = cls.replace('tag-', '').replace('-', ' ')
                if not subdomain:
                    subdomain = tag

        # Infer domain from subdomain
        if subdomain:
            domain = DomainInferencer._map_subdomain_to_domain(subdomain)

        return domain, subdomain

    @staticmethod
    def _infer_from_terms(categories: List, tags: List) -> Tuple[Optional[str], Optional[str]]:
        """Infer from categories and tags"""
        # Combine all terms
        all_terms = []

        if isinstance(categories, list):
            all_terms.extend([str(c).lower() for c in categories])
        if isinstance(tags, list):
            all_terms.extend([str(t).lower() for t in tags])

        if not all_terms:
            return None, None

        # Try to match domain keywords
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
        """Carefully infer from URL path segments, avoiding false positives."""
        # Avoid generic paths
        skip_terms = {
            'archive', 'archives', 'category', 'categories', 'tag', 'tags', 'page', 'author', 'date',
            'feed', 'wp', 'json', 'blog', 'post', 'posts', 'news'
        }
        try:
            # Extract path after domain
            m = re.match(r'^https?://[^/]+(/[^?#]*)', url)
            path = m.group(1) if m else ''
            # Split into segments
            segs = [s for s in re.split(r'[/_-]+', path) if s]
            # Filter segs: letters only, length >= 3, not numeric, not in skip
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
            # Score candidates against domain keywords
            scores = Counter()
            for s in cand:
                for dom, kws in DomainInferencer.DOMAIN_KEYWORDS.items():
                    if any(kw in s for kw in kws):
                        scores[(dom, s)] += 1
            if scores:
                # pick the (domain, sub) with highest score
                (dom, sub), _ = scores.most_common(1)[0]
                return dom, sub
            # Fallback: pick the first candidate and map
            sub = cand[0]
            dom = DomainInferencer._map_subdomain_to_domain(sub)
            if dom:
                return dom, sub
            return None, None
        except Exception:
            return None, None

    @staticmethod
    def _map_subdomain_to_domain(subdomain: str) -> Optional[str]:
        """Map subdomain to broader domain category"""
        subdomain = subdomain.lower()

        for domain, keywords in DomainInferencer.DOMAIN_KEYWORDS.items():
            if any(kw in subdomain for kw in keywords):
                return domain

        return None


# ============================================================================
# FILTERING
# ============================================================================

class RecordFilter:
    """Filter records based on pre and post filter rules"""

    @staticmethod
    def apply_pre_filter(record: Dict, config: CleaningConfig) -> Tuple[bool, str]:
        """Apply pre-processing filters. Returns (should_process, reason)"""
        pre_filter = config.pre_filter

        # Check URL patterns
        url = record.get('url', '')
        re_url_patterns = pre_filter.get('re_url', [])
        for pattern in re_url_patterns:
            if re.search(pattern, url, re.IGNORECASE):
                return False, f"url_pattern:{pattern}"

        # Check body length (will be checked after parsing)
        return True, ""

    @staticmethod
    def check_body_length(text: str, config: CleaningConfig) -> Tuple[bool, str]:
        """Check if cleaned body meets minimum length"""
        min_length = config.pre_filter.get('body_length', 200)
        if len(text) < min_length:
            return False, f"body_too_short:{len(text)}<{min_length}"
        return True, ""

    @staticmethod
    def apply_post_filter(title: str, cleaned_text: str, domain: str,
                          subdomain: str, config: CleaningConfig) -> Tuple[bool, str]:
        """Apply post-processing filters"""
        post_filter = config.post_filter

        # Check cleaned text patterns
        for pattern in post_filter.get('re_cleaned_text', []):
            if re.search(pattern, cleaned_text, re.IGNORECASE):
                return False, f"text_pattern:{pattern}"

        # Check title patterns
        for pattern in post_filter.get('re_title', []):
            if re.search(pattern, title, re.IGNORECASE):
                return False, f"title_pattern:{pattern}"

        # Check domain containing
        for term in post_filter.get('domain_containing', []):
            if term.lower() in domain.lower():
                return False, f"domain_contains:{term}"

        # Check subdomain containing
        for term in post_filter.get('subdomain_containing', []):
            if term.lower() in subdomain.lower():
                return False, f"subdomain_contains:{term}"

        return True, ""


# ============================================================================
# RECORD PROCESSOR
# ============================================================================

class RecordProcessor:
    """Process individual records"""

    def __init__(self, config_loader: ConfigLoader, sitekey: str):
        self.config_loader = config_loader
        self.config = config_loader.get_site_config(sitekey)
        self.cleaner = TextCleaner()
        # Reuse a trafilatura config per processor for performance
        try:
            self.trafilatura_config = use_config()
            self.trafilatura_config.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")
        except Exception:
            self.trafilatura_config = None

    def process_wordpress(self, record: Dict) -> Optional[Dict]:
        """Process WordPress format record"""
        try:
            # Pre-filter
            should_process, reason = RecordFilter.apply_pre_filter(record, self.config)
            if not should_process:
                return {'status': 'filtered_pre', 'reason': reason}

            # Parse body JSON (handle various shapes)
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

            # Extract fields
            url = record.get('url', '')
            record_id = record.get('id', str(uuid4()))
            meta = record.get('meta') or {}
            source_domain = meta.get('site', '') or meta.get('source', '') or ''
            if (not source_domain) and url:
                try:
                    # derive domain from URL if meta missing
                    source_domain = ConfigLoader._normalize_domain(url)
                except Exception:
                    source_domain = ''

            # Get title
            title_raw = (body or {}).get('title', {})
            if isinstance(title_raw, dict):
                title = title_raw.get('rendered', '') or ''
            elif title_raw is None:
                title = ''
            else:
                title = str(title_raw)

            # Get HTML content
            content_raw = (body or {}).get('content', {})
            if isinstance(content_raw, dict):
                body_html = content_raw.get('rendered', '') or ''
            elif content_raw is None:
                body_html = ''
            else:
                body_html = str(content_raw)

            # Apply cleaning pipeline
            cleaned_title = self._apply_cleaning_pipeline(title, is_title=True)

            # Extract clean text from HTML
            clean_args = self.config.clean.get('args', {})
            xpath = clean_args.get('body_xpath')
            noises = clean_args.get('noises', [])

            # Replace images, tables, and headings with placeholders and keep mapping
            html_with_placeholders, ph_map = preprocess_html_for_media(body_html, base_url=url)

            # Respect formatting args from config for links only; images/tables handled via placeholders
            formating = clean_args.get('formating', {})
            include_links = bool(formating.get('retain_links', False))

            # Run trafilatura on placeholder-embedded HTML; disable built-in images/tables
            extracted_body = self.cleaner.clean_html(
                html_with_placeholders,
                xpath,
                noises,
                include_tables=False,
                include_images=False,
                include_links=include_links,
                config=self.trafilatura_config,
            )

            # Restore placeholders to custom formats
            cleaned_body = restore_placeholders(extracted_body, ph_map)

            if not cleaned_body:
                return {'status': 'filtered_pre', 'reason': 'empty_after_extraction'}

            # Check body length
            should_process, reason = RecordFilter.check_body_length(cleaned_body, self.config)
            if not should_process:
                return {'status': 'filtered_pre', 'reason': reason}

            # Apply text cleaning
            cleaned_body = self._apply_cleaning_pipeline(cleaned_body, is_title=False)

            # Check English content if enabled
            if 'english_only' in self.config.clean.get('enabled', []):
                if not self.cleaner.is_english(cleaned_body):
                    return {'status': 'filtered_pre', 'reason': 'not_english'}

            # Infer domain/subdomain
            domain = self.config.domain_override
            subdomain = self.config.subdomain_override

            if not domain or not subdomain:
                inferred_domain, inferred_subdomain = DomainInferencer.infer_from_metadata(
                    body, self.config_loader, source_domain, url_hint=url, title_hint=cleaned_title, meta=meta
                )
                domain = domain or inferred_domain or self.config.domain_fallback
                subdomain = subdomain or inferred_subdomain or self.config.subdomain_fallback

            # Post-filter
            should_process, reason = RecordFilter.apply_post_filter(
                cleaned_title, cleaned_body, domain, subdomain, self.config
            )
            if not should_process:
                return {'status': 'filtered_post', 'reason': reason}

            # Build output
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
        """Apply enabled cleaning steps"""
        enabled = self.config.clean.get('enabled', [])

        if is_title:
            if 'clean_title' in enabled:
                text = self.cleaner.clean_title(text)
        else:
            if 'clean_html' in enabled:
                pass  # Already done in main processing

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
# FILE PROCESSOR
# ============================================================================

def process_file_worker(args: Tuple) -> Dict:
    """Worker function for processing a single file"""
    input_file, output_file, failed_file, config_path, sitekey, log_file_path, progress_file_path, progress_chunk = args

    # Initialize logging in worker to write into the same log file (no console)
    try:
        fh = logging.FileHandler(log_file_path, encoding='utf-8')
        fh.setLevel(logging.INFO)
        fh.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        root = logging.getLogger()
        root.addHandler(fh)
    except Exception:
        pass

    # Reinitialize in worker process
    config_loader = ConfigLoader(config_path)
    processor = RecordProcessor(config_loader, sitekey)

    stats = {
        'file': input_file.name,
        'total': 0,
        'success': 0,
        'failed': 0,
        'filtered_pre': 0,
        'filtered_post': 0
    }
    # Reason breakdowns
    reason_pre: Dict[str, int] = {}
    reason_post: Dict[str, int] = {}
    reason_err: Dict[str, int] = {}

    logging.info(f"Starting file: {input_file} -> {output_file} | failed-> {failed_file}")

    # Initialize progress snapshot
    try:
        progress_dir = Path(progress_file_path).parent
        progress_dir.mkdir(parents=True, exist_ok=True)
        with open(progress_file_path, 'w', encoding='utf-8') as pf:
            json.dump({
                'file': input_file.name,
                'status': 'running',
                'total': 0,
                'success': 0,
                'failed': 0,
                'filtered_pre': 0,
                'filtered_post': 0,
                'timestamp': time.time()
            }, pf, ensure_ascii=False)
    except Exception:
        pass

    try:
        with open(input_file, 'r', encoding='utf-8') as infile, \
                open(output_file, 'w', encoding='utf-8') as outfile, \
                open(failed_file, 'w', encoding='utf-8') as failfile:

            for line_num, line in enumerate(infile, 1):
                if not line.strip():
                    continue

                stats['total'] += 1

                try:
                    record = json.loads(line)
                    result = processor.process_wordpress(record)

                    if result['status'] == 'success':
                        outfile.write(json.dumps(result['data'], ensure_ascii=False) + '\n')
                        stats['success'] += 1
                    elif result['status'] == 'filtered_pre':
                        stats['filtered_pre'] += 1
                        reason = result['reason']
                        reason_pre[reason] = reason_pre.get(reason, 0) + 1
                        failfile.write(json.dumps({
                            'record': record,
                            'reason': reason,
                            'line': line_num
                        }, ensure_ascii=False) + '\n')
                    elif result['status'] == 'filtered_post':
                        stats['filtered_post'] += 1
                        reason = result['reason']
                        reason_post[reason] = reason_post.get(reason, 0) + 1
                        failfile.write(json.dumps({
                            'record': record,
                            'reason': reason,
                            'line': line_num
                        }, ensure_ascii=False) + '\n')
                    else:  # error
                        stats['failed'] += 1
                        reason = result.get('reason', 'unknown_error')
                        reason_err[reason] = reason_err.get(reason, 0) + 1
                        failfile.write(json.dumps({
                            'record': record,
                            'reason': reason,
                            'line': line_num
                        }, ensure_ascii=False) + '\n')

                except Exception as e:
                    stats['failed'] += 1
                    msg = str(e)
                    reason_err[msg] = reason_err.get(msg, 0) + 1
                    failfile.write(json.dumps({
                        'line': line_num,
                        'error': msg
                    }, ensure_ascii=False) + '\n')

                # Progress logging every chunk and snapshot write
                if stats['total'] % max(1, int(progress_chunk)) == 0:
                    logging.info(
                        f"{input_file.name}: processed {stats['total']} | "
                        f"success={stats['success']} pre={stats['filtered_pre']} post={stats['filtered_post']} failed={stats['failed']}"
                    )
                    try:
                        with open(progress_file_path, 'w', encoding='utf-8') as pf:
                            json.dump({
                                'file': input_file.name,
                                'status': 'running',
                                'total': stats['total'],
                                'success': stats['success'],
                                'failed': stats['failed'],
                                'filtered_pre': stats['filtered_pre'],
                                'filtered_post': stats['filtered_post'],
                                'timestamp': time.time()
                            }, pf, ensure_ascii=False)
                    except Exception:
                        pass

        # Detailed breakdown at end
        logging.info(
            f"Completed {input_file.name}: total={stats['total']} success={stats['success']} "
            f"pre={stats['filtered_pre']} post={stats['filtered_post']} failed={stats['failed']}"
        )
        if reason_pre:
            logging.info(f"{input_file.name} pre-filter reasons: {json.dumps(reason_pre, ensure_ascii=False)}")
        if reason_post:
            logging.info(f"{input_file.name} post-filter reasons: {json.dumps(reason_post, ensure_ascii=False)}")
        if reason_err:
            logging.info(f"{input_file.name} errors: {json.dumps(reason_err, ensure_ascii=False)}")

        # Write final progress snapshot
        try:
            with open(progress_file_path, 'w', encoding='utf-8') as pf:
                json.dump({
                    'file': input_file.name,
                    'status': 'done',
                    'total': stats['total'],
                    'success': stats['success'],
                    'failed': stats['failed'],
                    'filtered_pre': stats['filtered_pre'],
                    'filtered_post': stats['filtered_post'],
                    'timestamp': time.time()
                }, pf, ensure_ascii=False)
        except Exception:
            pass

        return stats

    except Exception as e:
        logging.error(f"File processing error for {input_file}: {e}")
        stats['failed'] = stats['total']
        # Error snapshot
        try:
            with open(progress_file_path, 'w', encoding='utf-8') as pf:
                json.dump({
                    'file': input_file.name,
                    'status': 'error',
                    'total': stats['total'],
                    'success': stats['success'],
                    'failed': stats['failed'],
                    'filtered_pre': stats['filtered_pre'],
                    'filtered_post': stats['filtered_post'],
                    'timestamp': time.time()
                }, pf, ensure_ascii=False)
        except Exception:
            pass
        return stats


# ============================================================================
# MAIN PIPELINE
# ============================================================================

class DataCleaningPipeline:
    """Main pipeline orchestrator"""

    def __init__(self, args):
        self.args = args
        self.config_loader = ConfigLoader(args.config)
        self.setup_logging()

    def setup_logging(self):
        """Setup logging configuration: detailed logs to file, warnings+ to terminal"""
        log_file = Path(self.args.log_dir) / f"cleaning_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        log_file.parent.mkdir(parents=True, exist_ok=True)
        # Save for worker processes
        self.log_file_path = str(log_file)

        # Create handlers explicitly to control levels
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        stream_handler = logging.StreamHandler(sys.stdout)
        stream_handler.setLevel(logging.WARNING)

        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        stream_handler.setFormatter(formatter)

        root = logging.getLogger()
        root.setLevel(logging.DEBUG)
        # Clear existing handlers added by previous runs
        root.handlers.clear()
        root.addHandler(file_handler)
        root.addHandler(stream_handler)

        # Reduce noise from libraries
        logging.getLogger('trafilatura').setLevel(logging.WARNING)
        logging.getLogger('urllib3').setLevel(logging.WARNING)

    def run(self):
        """Execute the pipeline"""
        input_dir = Path(self.args.input_dir)
        output_dir = Path(self.args.output_dir)
        failed_dir = Path(self.args.failed_dir)

        output_dir.mkdir(parents=True, exist_ok=True)
        failed_dir.mkdir(parents=True, exist_ok=True)

        # Discover input files
        input_files = list(input_dir.glob('*.jsonl'))

        if not input_files:
            logging.error(f"No .jsonl files found in {input_dir}")
            return

        logging.info(f"Found {len(input_files)} files to process")
        logging.info(f"Using {self.args.workers} workers")

        # Prepare tasks
        tasks = []
        # Make a progress directory inside log dir
        self.progress_dir = Path(self.args.log_dir) / 'progress'
        self.progress_dir.mkdir(parents=True, exist_ok=True)

        # Single-file acceleration: split the input into N chunks and process in parallel
        single_file_chunking = False
        chunk_dir = None
        final_output_target = None
        final_failed_target = None
        chunk_outputs: List[Path] = []
        chunk_faileds: List[Path] = []

        files_for_tasks: List[Path] = input_files
        original_sitekey: Optional[str] = None
        if len(input_files) == 1 and self.args.workers > 1:
            try:
                single_file_chunking = True
                original_file = input_files[0]
                original_sitekey = original_file.stem
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                chunk_dir = (Path(self.args.log_dir) / f"chunks_{original_sitekey}_{timestamp}")
                chunk_dir.mkdir(parents=True, exist_ok=True)

                # Create chunk writers
                n_workers = int(self.args.workers)
                chunk_paths = [chunk_dir / f"{original_sitekey}.part{i}.jsonl" for i in range(n_workers)]
                writers = [open(p, 'w', encoding='utf-8') for p in chunk_paths]
                try:
                    # Distribute lines round-robin to balance load
                    with open(original_file, 'r', encoding='utf-8') as src:
                        for idx, line in enumerate(src):
                            if not line.strip():
                                continue
                            writers[idx % n_workers].write(line)
                finally:
                    for w in writers:
                        try:
                            w.close()
                        except Exception:
                            pass
                files_for_tasks = chunk_paths

                # Set final targets (merged)
                final_output_target = output_dir / f"{original_sitekey}_cleaned.jsonl"
                final_failed_target = failed_dir / f"{original_sitekey}_failed.jsonl"
            except Exception as e:
                logging.warning(f"Chunking disabled due to error: {e}")
                single_file_chunking = False
                files_for_tasks = input_files

        for input_file in files_for_tasks:
            # Keep sitekey as original if chunking; otherwise derive from file
            sitekey = original_sitekey if (single_file_chunking and original_sitekey) else input_file.stem
            if single_file_chunking and chunk_dir is not None:
                # Direct chunk outputs to chunk_dir; we'll merge later
                chunk_out = chunk_dir / f"{input_file.stem}_cleaned.jsonl"
                chunk_fail = chunk_dir / f"{input_file.stem}_failed.jsonl"
                chunk_outputs.append(chunk_out)
                chunk_faileds.append(chunk_fail)
                output_file = chunk_out
                failed_file = chunk_fail
                progress_file = chunk_dir / f"{input_file.stem}.progress.json"
            else:
                output_file = output_dir / f"{sitekey}_cleaned.jsonl"
                failed_file = failed_dir / f"{sitekey}_failed.jsonl"
                progress_file = self.progress_dir / f"{sitekey}.progress.json"

            tasks.append((
                input_file,
                output_file,
                failed_file,
                self.args.config,
                sitekey,
                getattr(self, 'log_file_path', str(Path(self.args.log_dir) / 'cleaning.log')),
                str(progress_file),
                int(getattr(self.args, 'progress_chunk', 500))
            ))

        # Process files in parallel
        total_stats = {
            'total': 0,
            'success': 0,
            'failed': 0,
            'filtered_pre': 0,
            'filtered_post': 0
        }

        # Pre-scan files to determine line counts for per-file progress bars
        line_counts: Dict[str, int] = {}
        for task in tasks:
            try:
                with open(task[0], 'r', encoding='utf-8') as f:
                    line_counts[task[0].name] = sum(1 for _ in f)
            except Exception:
                line_counts[task[0].name] = 0

        # Initialize tqdm bars on-demand only for active files (up to number of workers)
        use_bars = tqdm is not None
        bars: Dict[str, Any] = {}
        bar_positions: Dict[str, int] = {}
        available_positions: List[int] = list(range(min(len(tasks), self.args.workers)))

        with ProcessPoolExecutor(max_workers=self.args.workers) as executor:
            futures = {executor.submit(process_file_worker, task): task[0].name for task in tasks}
            pending = set(futures.keys())

            last_print = 0.0
            progress_cache: Dict[str, Dict] = {}
            interval = float(getattr(self.args, 'progress_interval', 2.0))

            while pending:
                done, pending = wait(pending, timeout=interval, return_when=FIRST_COMPLETED)

                # Handle any completed futures
                for fut in done:
                    filename = futures[fut]
                    try:
                        stats = fut.result()
                        if not isinstance(stats, dict):
                            logging.error(f"✗ {filename}: worker returned invalid stats: {stats}")
                            continue
                        # Update totals
                        for key in total_stats:
                            total_stats[key] += int(stats.get(key, 0) or 0)
                        # Completion log
                        total = stats.get('total', 0) or 0
                        success = stats.get('success', 0) or 0
                        filtered_pre = stats.get('filtered_pre', 0) or 0
                        filtered_post = stats.get('filtered_post', 0) or 0
                        failed = stats.get('failed', 0) or 0
                        success_rate = (success / total * 100) if total > 0 else 0
                        # Emit a concise completion line above the bars
                        if use_bars and tqdm is not None:
                            tqdm.write(
                                f"✓ {filename}: {success}/{total} ({success_rate:.1f}%) | "
                                f"Filtered: {filtered_pre + filtered_post} | Failed: {failed}"
                            )
                        else:
                            logging.info(
                                f"✓ {filename}: {success}/{total} ({success_rate:.1f}%) | "
                                f"Filtered: {filtered_pre + filtered_post} | Failed: {failed}"
                            )
                        # Mark as done in progress cache
                        progress_cache[filename] = {
                            'file': filename,
                            'status': 'done',
                            'total': total,
                            'success': success,
                            'failed': failed,
                            'filtered_pre': filtered_pre,
                            'filtered_post': filtered_post,
                        }
                        # Finalize and remove progress bar for this file
                        if use_bars and filename in bars:
                            try:
                                bar = bars.pop(filename)
                                # ensure total is set for completion visuals if known
                                if bar.total is None and line_counts.get(filename, 0) > 0:
                                    bar.total = line_counts[filename]
                                bar.n = bar.total if bar.total is not None else total
                                bar.refresh()
                                bar.close()
                            except Exception:
                                pass
                            # free its position for reuse
                            pos = bar_positions.pop(filename, None)
                            if pos is not None and pos not in available_positions:
                                available_positions.append(pos)
                    except Exception as e:
                        logging.error(f"✗ {filename}: {e}")

                # Periodic progress display
                now = time.time()
                if now - last_print >= interval:
                    aggregated = {'total': 0, 'success': 0, 'failed': 0, 'filtered_pre': 0, 'filtered_post': 0}
                    in_progress = []
                    # Load snapshots
                    for task in tasks:
                        file_name = task[0].name
                        progress_file = Path(task[6])  # progress file path passed to worker
                        snap = progress_cache.get(file_name)
                        if progress_file.exists():
                            try:
                                with open(progress_file, 'r', encoding='utf-8') as pf:
                                    snap = json.load(pf)
                                    progress_cache[file_name] = snap
                            except Exception:
                                pass
                        if snap and isinstance(snap, dict):
                            processed = int(snap.get('total', 0) or 0)
                            aggregated['total'] += processed
                            aggregated['success'] += int(snap.get('success', 0) or 0)
                            aggregated['failed'] += int(snap.get('failed', 0) or 0)
                            aggregated['filtered_pre'] += int(snap.get('filtered_pre', 0) or 0)
                            aggregated['filtered_post'] += int(snap.get('filtered_post', 0) or 0)
                            status = snap.get('status')
                            if status != 'done':
                                in_progress.append(f"{file_name}:{processed}")
                            # Manage tqdm bar for this file
                            if use_bars:
                                # Create bar lazily for active tasks
                                if status != 'done' and file_name not in bars and available_positions:
                                    try:
                                        pos = available_positions.pop(0)
                                        bar_positions[file_name] = pos
                                        total = line_counts.get(file_name, 0)
                                        bar_total = total if total > 0 else None
                                        bars[file_name] = tqdm(
                                            total=bar_total,
                                            desc=file_name,
                                            position=pos,
                                            leave=False,
                                            unit='rec',
                                            dynamic_ncols=True
                                        )
                                    except Exception:
                                        pass
                                # Update existing bar
                                if file_name in bars:
                                    bar = bars[file_name]
                                    if processed >= getattr(bar, 'n', 0):
                                        bar.n = processed
                                        try:
                                            bar.refresh()
                                        except Exception:
                                            pass
                                    # Close and free finished bars
                                    if status == 'done':
                                        try:
                                            bar = bars.pop(file_name)
                                            # ensure completion visual
                                            if bar.total is None and line_counts.get(file_name, 0) > 0:
                                                bar.total = line_counts[file_name]
                                            if bar.total is not None and bar.n < bar.total:
                                                bar.n = bar.total
                                            bar.refresh()
                                            bar.close()
                                        except Exception:
                                            pass
                                        pos = bar_positions.pop(file_name, None)
                                        if pos is not None and pos not in available_positions:
                                            available_positions.append(pos)
                    # If tqdm is not available, print a single updating line
                    if not use_bars:
                        line = (
                            f"Progress: processed={aggregated['total']:,} | "
                            f"success={aggregated['success']:,} pre={aggregated['filtered_pre']:,} "
                            f"post={aggregated['filtered_post']:,} failed={aggregated['failed']:,}"
                        )
                        if in_progress:
                            line += " | files: " + ", ".join(in_progress[:5]) + (" ..." if len(in_progress) > 5 else "")
                        print("\r" + line, end="", flush=True)
                    last_print = now

            # Ensure newline after progress line if not using bars
            if not use_bars:
                print()

        # Close any remaining bars (safety)
        if use_bars:
            for bar in bars.values():
                try:
                    bar.close()
                except Exception:
                    pass

        # If we chunked a single file, merge the chunk outputs into final targets
        if single_file_chunking and chunk_dir is not None and final_output_target is not None and final_failed_target is not None:
            try:
                # Merge cleaned outputs
                with open(final_output_target, 'w', encoding='utf-8') as fout:
                    for p in chunk_outputs:
                        try:
                            with open(p, 'r', encoding='utf-8') as fin:
                                for line in fin:
                                    fout.write(line)
                        except Exception as e:
                            logging.warning(f"Failed to merge chunk output {p}: {e}")
                # Merge failed outputs
                with open(final_failed_target, 'w', encoding='utf-8') as ff:
                    for p in chunk_faileds:
                        try:
                            with open(p, 'r', encoding='utf-8') as fin:
                                for line in fin:
                                    ff.write(line)
                        except Exception as e:
                            logging.warning(f"Failed to merge chunk failed {p}: {e}")
                logging.info(f"Merged chunk outputs to {final_output_target} and {final_failed_target}")
            except Exception as e:
                logging.error(f"Failed to merge chunked outputs: {e}")

        # Final summary
        self.print_summary(total_stats)

    def print_summary(self, stats: Dict):
        """Print final processing summary"""
        print("\n" + "=" * 70)
        print("PROCESSING SUMMARY")
        print("=" * 70)
        print(f"Total Records:        {stats['total']:,}")
        print(f"Successfully Cleaned: {stats['success']:,}")
        print(f"Pre-filtered:         {stats['filtered_pre']:,}")
        print(f"Post-filtered:        {stats['filtered_post']:,}")
        print(f"Failed:               {stats['failed']:,}")

        if stats['total'] > 0:
            success_rate = stats['success'] / stats['total'] * 100
            print(f"\nSuccess Rate:         {success_rate:.2f}%")

        print("=" * 70)

        logging.info(f"Pipeline completed: {json.dumps(stats)}")


# ============================================================================
# COMMAND LINE INTERFACE
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='High-Performance Data Cleaning Pipeline',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Process all files in input directory with 16 workers
  python data_cleaner.py -i ./raw_data -o ./cleaned_data -w 16

  # Use custom config file
  python data_cleaner.py -i ./raw_data -o ./cleaned_data -c custom_config.yaml

  # Specify failed records directory
  python data_cleaner.py -i ./raw_data -o ./cleaned_data -f ./failed_records
        """
    )

    parser.add_argument(
        '-i', '--input-dir',
        type=str,
        default='./input',
        help='Input directory containing .jsonl files (default: ./input)'
    )

    parser.add_argument(
        '-o', '--output-dir',
        type=str,
        default='./output',
        help='Output directory for cleaned files (default: ./output)'
    )

    parser.add_argument(
        '-f', '--failed-dir',
        type=str,
        default='./failed',
        help='Directory for failed/filtered records (default: ./failed)'
    )

    parser.add_argument(
        '-c', '--config',
        type=str,
        default='cleaning_map.yaml',
        help='Path to configuration YAML file (default: cleaning_map.yaml)'
    )

    parser.add_argument(
        '-w', '--workers',
        type=int,
        default=cpu_count(),
        help=f'Number of parallel workers (default: {cpu_count()} - all cores)'
    )

    parser.add_argument(
        '-l', '--log-dir',
        type=str,
        default='./logs',
        help='Directory for log files (default: ./logs)'
    )

    parser.add_argument(
        '--progress-interval',
        type=float,
        default=2.0,
        help='Seconds between console progress updates (default: 2.0)'
    )

    parser.add_argument(
        '--progress-chunk',
        type=int,
        default=500,
        help='Records between worker progress snapshots (default: 500)'
    )

    parser.add_argument(
        '--version',
        action='version',
        version='Data Cleaning Pipeline v1.0'
    )

    args = parser.parse_args()

    # Run pipeline
    pipeline = DataCleaningPipeline(args)
    pipeline.run()


if __name__ == '__main__':
    main()