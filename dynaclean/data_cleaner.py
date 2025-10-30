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
from concurrent.futures import ProcessPoolExecutor, as_completed, wait, FIRST_COMPLETED
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
                            'retain_image': True
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

    def get_domain_mapping(self, source_domain: str) -> Tuple[Optional[str], Optional[str]]:
        """Get domain/subdomain from mapping"""
        domain_map = self.config.get('domain_mapping', {})
        mapping = domain_map.get(source_domain, {})
        return mapping.get('domain'), mapping.get('subdomain')


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
    ) -> str:
        """Extract clean text from HTML using trafilatura.
        - Supports true XPath pre-selection (not CSS).
        - Respects include_tables/images/links flags from config.
        """
        if not html or not html.strip():
            return ""

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
                            source_domain: str) -> Tuple[str, str]:
        """
        Infer domain/subdomain with priority:
        1. Config override
        2. Domain mapping
        3. Trafilatura metadata
        4. Class list extraction
        5. URL inference
        6. Fallback
        """
        # Check domain mapping first
        mapped_domain, mapped_subdomain = config_loader.get_domain_mapping(source_domain)
        if mapped_domain and mapped_subdomain:
            return mapped_domain, mapped_subdomain

        # Try to extract from categories in class_list
        class_list = body_json.get('class_list', [])
        if isinstance(class_list, list):
            domain, subdomain = DomainInferencer._extract_from_classes(class_list)
            if domain and subdomain:
                return domain, subdomain

        # Try categories and tags from body
        categories = body_json.get('categories', [])
        tags = body_json.get('tags', [])

        if categories or tags:
            domain, subdomain = DomainInferencer._infer_from_terms(categories, tags)
            if domain and subdomain:
                return domain, subdomain

        # Try URL inference as last resort
        url = body_json.get('link', '')
        if url:
            domain, subdomain = DomainInferencer._infer_from_url(url)
            if domain and subdomain:
                return domain, subdomain

        return None, None

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
        """Carefully infer from URL, avoiding false positives"""
        # Avoid generic paths
        skip_patterns = ['archive', 'category', 'tag', 'page', 'author', 'date']

        # Extract path segments
        path_match = re.search(r'https?://[^/]+/([^/?#]+)', url)
        if not path_match:
            return None, None

        segment = path_match.group(1).lower()

        # Skip if it's a generic pattern
        if any(pattern in segment for pattern in skip_patterns):
            return None, None

        # Try to map to domain
        domain = DomainInferencer._map_subdomain_to_domain(segment)
        return domain, segment if domain else (None, None)

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

            # Respect formatting args from config
            formating = clean_args.get('formating', {})
            include_tables = bool(formating.get('retain_table', True))
            include_images = bool(formating.get('retain_image', True))
            include_links = bool(formating.get('retain_links', False))

            cleaned_body = self.cleaner.clean_html(
                body_html,
                xpath,
                noises,
                include_tables=include_tables,
                include_images=include_images,
                include_links=include_links,
            )

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
                    body, self.config_loader, source_domain
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
        for input_file in input_files:
            sitekey = input_file.stem  # filename without extension
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

        # Initialize tqdm bars if available
        use_bars = tqdm is not None
        bars: Dict[str, Any] = {}
        if use_bars:
            for idx, task in enumerate(tasks):
                fname = task[0].name
                total = line_counts.get(fname, 0)
                # If total unknown (0), let tqdm handle indefinite total
                bar_total = total if total > 0 else None
                bars[fname] = tqdm(
                    total=bar_total,
                    desc=fname,
                    position=idx,
                    leave=True,
                    unit='rec',
                    dynamic_ncols=True
                )

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
                        # Finalize progress bar for this file
                        if use_bars and filename in bars:
                            bar = bars[filename]
                            if bar.total is None and line_counts.get(filename, 0) > 0:
                                bar.total = line_counts[filename]
                            # Ensure bar shows as complete
                            bar.n = bar.total if bar.total is not None else total
                            bar.refresh()
                            bar.close()
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
                            if snap.get('status') != 'done':
                                in_progress.append(f"{file_name}:{processed}")
                            # Update tqdm bar for this file
                            if use_bars and file_name in bars:
                                bar = bars[file_name]
                                if processed >= bar.n:
                                    bar.n = processed
                                    bar.refresh()
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