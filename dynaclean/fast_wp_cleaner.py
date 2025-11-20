#!/usr/bin/env python3
"""
ULTRA-FAST WordPress Data Cleaner
Optimized for 6000 files, 1MB-10GB each, 20 cores, 64GB RAM
Target: 1000+ records/second
"""

import json
import re
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count, Manager
import sys
import time
from collections import defaultdict

try:
    from tqdm.auto import tqdm
except ImportError:
    tqdm = None

try:
    from trafilatura import extract
    from trafilatura.settings import use_config
    from lxml import html as lxml_html, etree
    from uuid import uuid4
except ImportError:
    print("ERROR: Install dependencies:")
    print("pip install trafilatura lxml tqdm pyyaml")
    sys.exit(1)


# ============================================================================
# PRE-COMPILED PATTERNS (CRITICAL FOR SPEED)
# ============================================================================

class FastPatterns:
    """All regex patterns pre-compiled once at module load"""

    # Email anonymization
    EMAIL = re.compile(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b')

    # Emoji removal
    EMOJI = re.compile(
        "["
        "\U0001F600-\U0001F64F"
        "\U0001F300-\U0001F5FF"
        "\U0001F680-\U0001F6FF"
        "\U0001F1E0-\U0001F1FF"
        "\U00002702-\U000027B0"
        "\U000024C2-\U0001F251"
        "]+", flags=re.UNICODE
    )

    # Whitespace normalization
    MULTI_SPACE = re.compile(r' +')
    MULTI_NEWLINE = re.compile(r'\n\s*\n\s*\n+')

    # Punctuation cleanup
    EXCESSIVE_PUNCT = re.compile(r'([!?.]){3,}')

    # URL filtering patterns (pre-compiled)
    FILTER_URL_PATTERNS = [
        re.compile(r'/contact/', re.I),
        re.compile(r'/about/', re.I),
        re.compile(r'/privacy-policy/', re.I),
        re.compile(r'/terms-of-service/', re.I),
    ]

    # Title filtering patterns
    FILTER_TITLE_PATTERNS = [
        re.compile(r'podcast', re.I),
        re.compile(r'\[sponsored\]', re.I),
        re.compile(r'webinar', re.I),
        re.compile(r'livestream', re.I),
    ]

    # HTML entities
    HTML_ENTITY = re.compile(r'&#?\w+;')

    # Noise removal (fast string matching, not XPath)
    NOISE_PATTERNS = [
        re.compile(r'<header[^>]*>.*?</header>', re.I | re.DOTALL),
        re.compile(r'<footer[^>]*>.*?</footer>', re.I | re.DOTALL),
        re.compile(r'<nav[^>]*>.*?</nav>', re.I | re.DOTALL),
        re.compile(r'<aside[^>]*>.*?</aside>', re.I | re.DOTALL),
        # Common site chrome and CTAs by class hints
        re.compile(
            r'<(?:div|section|ul|ol)[^>]*class="[^"]*(?:breadcrumb|share|share-this|social|follow|newsletter|subscribe|cookie|gdpr|related|related-posts|post-navigation|nav-links|comments?|comment-form|ad-|affiliate|sponsored|disclosure|toc|table-of-contents|read-?more|also-?read|btn|button|print-recipe)[^"]*"[^>]*>.*?</(?:div|section|ul|ol)>',
            re.I | re.DOTALL),
        re.compile(r'<script[^>]*>.*?</script>', re.I | re.DOTALL),
        re.compile(r'<style[^>]*>.*?</style>', re.I | re.DOTALL),
        re.compile(r'<noscript[^>]*>.*?</noscript>', re.I | re.DOTALL),
    ]

    # Text-level CTA/boilerplate removal patterns (applied after extraction)
    CTA_TEXT_PATTERNS = [
        re.compile(r'\bclick here\b', re.I),
        re.compile(r'\bshare this (?:post|article)\b', re.I),
        re.compile(r'\bvisit (?:this|our) (?:site|link|website)\b', re.I),
        re.compile(r'\bshare your comments? below\b', re.I),
        re.compile(r'\bsign up to\b', re.I),
        re.compile(r'\bsign up for\b', re.I),
        re.compile(r'\bsubscribe (?:now|to (?:our|the) newsletter)\b', re.I),
        re.compile(r'\bfollow (?:me|us) (?:on|at)\b', re.I),
        re.compile(r'\b(disclosure|affiliate(?: links?)?|sponsored)(?:[^\n]{0,80})', re.I),
        re.compile(r'\bread (?:also|more)\b', re.I),
        re.compile(r'\balso read\b', re.I),
        re.compile(r'\bwatch (?:on )?youtube\b', re.I),
        re.compile(r'\bprint recipe\b', re.I),
        re.compile(r'\bleave a comment\b', re.I),
        re.compile(r'\bcomments? (?:are )?closed\b', re.I),
    ]


# ============================================================================
# FAST DOMAIN MAPPER (O(1) LOOKUP)
# ============================================================================

class FastDomainMapper:
    """Lightning-fast domain mapping with pre-normalized keys"""

    def __init__(self, mapping_file: str = 'domain_mapping.json'):
        self.mapping = {}
        self.load_mapping(mapping_file)

    def load_mapping(self, filepath: str):
        """Load domain mapping from JSON (faster than YAML)"""
        path = Path(filepath)
        if not path.exists():
            logging.warning(f"Domain mapping file {filepath} not found")
            return

        try:
            with open(path, 'r', encoding='utf-8') as f:
                raw = json.load(f)
                # Pre-normalize all keys for O(1) lookup
                for domain, mapping in raw.items():
                    normalized = self._normalize(domain)
                    self.mapping[normalized] = (
                        mapping.get('domain', 'daily life'),
                        mapping.get('subdomain', 'living')
                    )
            logging.info(f"Loaded {len(self.mapping)} domain mappings")
        except Exception as e:
            logging.error(f"Failed to load domain mapping: {e}")

    @staticmethod
    def _normalize(domain: str) -> str:
        """Ultra-fast domain normalization"""
        if not domain:
            return ''
        d = domain.lower().strip()
        # Remove protocol
        if d.startswith('http'):
            d = d.split('://', 1)[-1]
        # Remove path and port
        d = d.split('/')[0].split(':')[0]
        # Remove www.
        if d.startswith('www.'):
            d = d[4:]
        return d

    def get(self, domain: str) -> Tuple[str, str]:
        """Get domain/subdomain mapping (O(1) lookup)"""
        normalized = self._normalize(domain)
        return self.mapping.get(normalized, ('daily life', 'living'))


# ============================================================================
# ULTRA-FAST TEXT CLEANER
# ============================================================================

class UltraFastCleaner:
    """Optimized text cleaning with minimal object creation"""

    @staticmethod
    def clean_html_noise(html: str) -> str:
        """Remove noise BEFORE trafilatura for faster parsing"""
        if not html:
            return ''

        # Fast string-based noise removal (faster than XPath)
        for pattern in FastPatterns.NOISE_PATTERNS:
            html = pattern.sub('', html)

        return html

    @staticmethod
    def extract_clean_text(html: str, config) -> str:
        """Fast trafilatura extraction"""
        if not html:
            return ''

        # Pre-clean HTML
        html = UltraFastCleaner.clean_html_noise(html)

        # Fast extraction
        extracted = extract(
            html,
            config=config,
            include_tables=False,  # We handle tables separately
            include_images=False,  # We handle images separately
            include_links=False,
            favor_precision=True,
            include_comments=False,
        )

        return extracted or ''

    @staticmethod
    def process_media(html: str, url: str = '', remove_xpaths: Optional[List[str]] = None) -> Tuple[str, Dict]:
        """Extract and replace tables/images with placeholders, optionally remove nodes by XPath"""
        if not html:
            return '', {}

        from urllib.parse import urljoin

        mapping = {}

        try:
            doc = lxml_html.fromstring(html)
        except:
            return html, {}

        # Apply XPath-based removals if provided
        if remove_xpaths:
            for xp in remove_xpaths:
                try:
                    for node in doc.xpath(xp):
                        parent = node.getparent()
                        if parent is not None:
                            parent.remove(node)
                except Exception:
                    continue

        # Process tables -> LaTeX
        for idx, table in enumerate(doc.xpath('.//table')):
            placeholder = f"[[TABLE_{idx}]]"
            latex = UltraFastCleaner._table_to_latex(table)
            if latex:
                mapping[placeholder] = latex
                table.getparent().replace(table, lxml_html.fromstring(f'<p>{placeholder}</p>'))

        # Process images -> [Image: url]
        for idx, img in enumerate(doc.xpath('.//img')):
            placeholder = f"[[IMAGE_{idx}]]"
            src = UltraFastCleaner._get_best_image_src(img)
            if src and not UltraFastCleaner._is_placeholder_img(src):
                if url:
                    src = urljoin(url, src)
                mapping[placeholder] = f"[Image: {src}\\]"
                img.getparent().replace(img, lxml_html.fromstring(f'<span>{placeholder}</span>'))

        return etree.tostring(doc, encoding='unicode'), mapping

    @staticmethod
    def _table_to_latex(table_elem) -> str:
        """Fast table -> LaTeX conversion"""
        rows = []
        for tr in table_elem.xpath('.//tr'):
            cells = []
            for cell in tr.xpath('./th | ./td'):
                text = ' '.join(cell.itertext()).strip()
                # Fast LaTeX escape
                text = text.replace('\\', r'\\').replace('&', r'\&').replace('%', r'\%')
                text = text.replace('$', r'\$').replace('#', r'\#').replace('_', r'\_')
                cells.append(text)
            if cells:
                rows.append(cells)

        if not rows:
            return ''

        ncols = max(len(r) for r in rows)
        lines = [
            f"\\begin{{tabular}}{{|{'|'.join(['l'] * ncols)}|}}",
            "\\hline"
        ]

        for row in rows:
            row += [''] * (ncols - len(row))  # Pad
            lines.append(' & '.join(row) + r' \\')
            lines.append("\\hline")

        lines.append("\\end{tabular}")
        return '\n'.join(lines)

    @staticmethod
    def _get_best_image_src(img) -> str:
        """Get best image source from img tag"""
        # Priority order
        attrs = ['data-src', 'data-original', 'src']
        for attr in attrs:
            val = img.get(attr)
            if val:
                return val
        return ''

    @staticmethod
    def _is_placeholder_img(src: str) -> bool:
        """Check if image is placeholder"""
        if not src:
            return True
        src_lower = src.lower()
        return any(x in src_lower for x in ['placeholder', 'blank', 'data:image', '1x1'])

    @staticmethod
    def restore_media(text: str, mapping: Dict) -> str:
        """Restore media placeholders"""
        for placeholder, value in mapping.items():
            text = text.replace(placeholder, value)
        return text

    @staticmethod
    def normalize_unicode(text: str) -> str:
        """Fast unicode normalization"""
        if not text:
            return ''

        import unicodedata
        text = unicodedata.normalize('NFKC', text)

        # Fast replacements
        replacements = {
            '\u2018': "'", '\u2019': "'", '\u201C': '"', '\u201D': '"',
            '\u2013': '-', '\u2014': '-', '\u00A0': ' ', '\u200B': '',
        }

        for old, new in replacements.items():
            text = text.replace(old, new)

        return text

    @staticmethod
    def anonymize_email(text: str) -> str:
        """Fast email anonymization"""

        def repl(m):
            email = m.group(0)
            parts = email.split('@')
            if len(parts) != 2:
                return email
            return 'x' * len(parts[0]) + '@' + 'x' * len(parts[1])

        return FastPatterns.EMAIL.sub(repl, text)

    @staticmethod
    def clean_all(text: str) -> str:
        """Apply all fast cleaning steps"""
        if not text:
            return ''

        # Pipeline (order matters for performance)
        text = UltraFastCleaner.normalize_unicode(text)
        text = FastPatterns.EMOJI.sub('', text)
        text = UltraFastCleaner.anonymize_email(text)
        # Remove common CTA/boilerplate snippets
        try:
            for p in getattr(FastPatterns, 'CTA_TEXT_PATTERNS', []) or []:
                text = p.sub(' ', text)
        except Exception:
            pass
        text = FastPatterns.EXCESSIVE_PUNCT.sub(r'\1\1', text)
        text = FastPatterns.MULTI_SPACE.sub(' ', text)
        text = FastPatterns.MULTI_NEWLINE.sub('\n\n', text)

        return text.strip()

    @staticmethod
    def clean_title(title: str) -> str:
        """Fast title cleaning"""
        if not title:
            return ''
        title = FastPatterns.HTML_ENTITY.sub(' ', title)
        title = FastPatterns.MULTI_SPACE.sub(' ', title)
        return title.strip()


# ============================================================================
# FAST FILTERS
# ============================================================================

class FastFilter:
    """Pre-filter and post-filter with compiled patterns"""

    @staticmethod
    def should_skip_url(url: str) -> bool:
        """Fast URL filtering"""
        return any(p.search(url) for p in FastPatterns.FILTER_URL_PATTERNS)

    @staticmethod
    def should_skip_title(title: str) -> bool:
        """Fast title filtering"""
        return any(p.search(title) for p in FastPatterns.FILTER_TITLE_PATTERNS)

    @staticmethod
    def is_english(text: str, threshold: float = 0.7) -> bool:
        """Fast English detection"""
        if not text or len(text) < 50:
            return True

        # Sample for speed (first 500 chars)
        sample = text[:500]
        ascii_letters = sum(1 for c in sample if c.isascii() and c.isalpha())
        total_letters = sum(1 for c in sample if c.isalpha())

        if total_letters == 0:
            return False

        return (ascii_letters / total_letters) >= threshold


# ============================================================================
# WORKER PROCESS
# ============================================================================

# Global objects (initialized once per worker)
_TRAFILATURA_CONFIG = None
_DOMAIN_MAPPER = None
_NOISE_RULES = None


def init_worker(domain_mapping_file: str, noise_rules_file: Optional[str] = None):
    """Initialize worker process (called once per worker)"""
    global _TRAFILATURA_CONFIG, _DOMAIN_MAPPER, _NOISE_RULES

    # Setup trafilatura config
    _TRAFILATURA_CONFIG = use_config()
    _TRAFILATURA_CONFIG.set("DEFAULT", "EXTRACTION_TIMEOUT", "0")

    # Load domain mapper
    _DOMAIN_MAPPER = FastDomainMapper(domain_mapping_file)

    # Load noise rules once per worker
    _NOISE_RULES = None
    if noise_rules_file:
        try:
            path = Path(noise_rules_file)
            if path.exists():
                with open(path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                # Build mapping host -> list[xpath]
                site_rules = {}
                for site_key, site_data in (cfg.get('site_specific') or {}).items():
                    xps = [x.get('xpath') for x in (site_data.get('suggested_xpaths') or []) if x.get('xpath')]
                    if xps:
                        site_rules[site_key] = xps
                # If config has flattened list, use; else collect from global_xpaths
                global_rules = [x.get('xpath') for x in (cfg.get('flattened_xpaths') or []) if x.get('xpath')] or \
                                [x.get('xpath') for x in (cfg.get('global_xpaths') or []) if x.get('xpath')]
                _NOISE_RULES = {'global': global_rules, 'site': site_rules}
        except Exception as e:
            logging.warning(f"Failed to load noise rules: {e}")


def process_batch(batch_data: Tuple) -> Dict:
    """Process a batch of records (runs in worker process)"""
    lines, seen_urls = batch_data

    stats = {
        'success': 0,
        'duplicate': 0,
        'filtered': 0,
        'failed': 0
    }

    results = []

    for line in lines:
        try:
            # Fast JSON decode
            record = json.loads(line)
        except:
            stats['failed'] += 1
            continue

        try:
            result = process_single_record(record, seen_urls)

            if result['status'] == 'success':
                results.append(result['data'])
                stats['success'] += 1
            elif result['status'] == 'duplicate':
                stats['duplicate'] += 1
            elif result['status'] == 'filtered':
                stats['filtered'] += 1
            else:
                stats['failed'] += 1

        except Exception as e:
            stats['failed'] += 1
            logging.debug(f"Process error: {e}")

    return {'results': results, 'stats': stats}


def _site_key_from_url(url: str) -> str:
    if not url:
        return ''
    u = url.lower()
    if '://' in u:
        u = u.split('://', 1)[-1]
    host = u.split('/')[0]
    if host.startswith('www.'):
        host = host[4:]
    return host.replace('.', '_')


def _noise_xpaths_for_url(url: str) -> List[str]:
    global _NOISE_RULES
    if not _NOISE_RULES:
        return []
    sk = _site_key_from_url(url)
    result = []
    # site specific
    site_map = _NOISE_RULES.get('site') or {}
    if sk in site_map:
        result.extend(site_map.get(sk) or [])
    # global fallbacks
    result.extend(_NOISE_RULES.get('global') or [])
    # Deduplicate preserving order
    seen = set()
    deduped = []
    for xp in result:
        if xp and xp not in seen:
            seen.add(xp)
            deduped.append(xp)
    return deduped


def process_single_record(record: Dict, seen_urls: 'Manager.dict') -> Dict:
    """Process a single WordPress record"""
    global _TRAFILATURA_CONFIG, _DOMAIN_MAPPER

    # Extract data
    url = record.get('url', '')

    # Pre-filter: URL check
    if FastFilter.should_skip_url(url):
        return {'status': 'filtered'}

    # Deduplication
    if url in seen_urls:
        return {'status': 'duplicate'}

    # Parse body
    body_raw = record.get('body', '{}')
    if isinstance(body_raw, str):
        try:
            body = json.loads(body_raw)
        except:
            return {'status': 'failed'}
    else:
        body = body_raw

    # Extract title
    title_raw = body.get('title', {})
    if isinstance(title_raw, dict):
        title = title_raw.get('rendered', '')
    else:
        title = str(title_raw) if title_raw else ''

    # Clean title
    title = UltraFastCleaner.clean_title(title)

    # Filter: Title check
    if FastFilter.should_skip_title(title):
        return {'status': 'filtered'}

    # Extract content
    content_raw = body.get('content', {})
    if isinstance(content_raw, dict):
        html = content_raw.get('rendered', '')
    else:
        html = str(content_raw) if content_raw else ''

    if not html or len(html) < 100:
        return {'status': 'filtered'}

    # Process media (tables/images)
    # Determine optional noise XPath removals
    remove_xpaths = _noise_xpaths_for_url(url)

    html_with_placeholders, media_mapping = UltraFastCleaner.process_media(html, url, remove_xpaths=remove_xpaths)

    # Extract clean text
    extracted = UltraFastCleaner.extract_clean_text(html_with_placeholders, _TRAFILATURA_CONFIG)

    if not extracted or len(extracted) < 200:
        return {'status': 'filtered'}

    # Restore media
    text = UltraFastCleaner.restore_media(extracted, media_mapping)

    # Apply cleaning pipeline
    text = UltraFastCleaner.clean_all(text)

    # Filter: Length and language
    if len(text) < 200:
        return {'status': 'filtered'}

    if not FastFilter.is_english(text):
        return {'status': 'filtered'}

    # Get domain mapping
    meta = record.get('meta', {})
    source_domain = meta.get('site', '') or meta.get('source', '')
    if not source_domain and url:
        source_domain = FastDomainMapper._normalize(url)

    domain, subdomain = _DOMAIN_MAPPER.get(source_domain)

    # Mark URL as seen
    seen_urls[url] = 1

    # Build output
    output = {
        'id': record.get('id', str(uuid4())),
        'text': f"{title}\n{text}",
        'meta': {
            'data_info': {
                'lang': 'en',
                'url': url,
                'source': source_domain,
                'type': 'website content',
                'processing_date': datetime.now().isoformat(),
                'delivery_version': 'v1',
                'title': title
            },
            'content_info': {
                'domain': domain,
                'subdomain': subdomain
            }
        }
    }

    return {'status': 'success', 'data': output}


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def process_file(filepath: Path, output_file: Path, domain_mapping_file: str,
                 workers: int, batch_size: int, noise_config: Optional[str] = None) -> Dict:
    """Process a single file with all cores"""

    print(f"\nProcessing: {filepath.name}")
    start = time.time()

    stats = defaultdict(int)

    # Read file into batches
    batches = []
    current_batch = []

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                current_batch.append(line)
                stats['total'] += 1

                if len(current_batch) >= batch_size:
                    batches.append(current_batch)
                    current_batch = []

            if current_batch:
                batches.append(current_batch)

    except Exception as e:
        print(f"ERROR reading {filepath.name}: {e}")
        return stats

    if not batches:
        print(f"No records in {filepath.name}")
        return stats

    # Process with multiprocessing
    with Manager() as manager:
        seen_urls = manager.dict()

        with ProcessPoolExecutor(
                max_workers=workers,
                initializer=init_worker,
                initargs=(domain_mapping_file, noise_config)
        ) as executor:

            # Submit all batches
            futures = [
                executor.submit(process_batch, (batch, seen_urls))
                for batch in batches
            ]

            # Collect results with progress bar
            pbar = tqdm(total=len(batches), desc=filepath.stem, unit='batch') if tqdm else None

            with open(output_file, 'w', encoding='utf-8') as out:
                for future in as_completed(futures):
                    try:
                        result = future.result()

                        # Write results
                        for record in result['results']:
                            out.write(json.dumps(record, ensure_ascii=False) + '\n')

                        # Update stats
                        for key, value in result['stats'].items():
                            stats[key] += value

                        if pbar:
                            pbar.update(1)

                    except Exception as e:
                        logging.error(f"Batch processing error: {e}")
                        if pbar:
                            pbar.update(1)

            if pbar:
                pbar.close()

    elapsed = time.time() - start
    speed = stats['total'] / elapsed if elapsed > 0 else 0

    print(f"✓ {filepath.name}: {stats['success']:,} success, "
          f"{stats['filtered']:,} filtered, {stats['duplicate']:,} duplicates | "
          f"{speed:.0f} rec/s")

    return stats


def main():
    parser = argparse.ArgumentParser(description='Ultra-Fast WordPress Data Cleaner')
    parser.add_argument('-i', '--input-dir', type=str, default='./input')
    parser.add_argument('-o', '--output-dir', type=str, default='./output')
    parser.add_argument('-d', '--domain-mapping', type=str, default='domain_mapping.json',
                        help='Domain mapping file (JSON format for speed)')
    parser.add_argument('-w', '--workers', type=int, default=cpu_count(),
                        help=f'Worker processes (default: {cpu_count()})')
    parser.add_argument('-b', '--batch-size', type=int, default=200,
                        help='Records per batch (default: 200)')
    parser.add_argument('-n', '--noise-config', type=str, default=None,
                        help='Optional noise analyzer JSON output to remove site/global noise before extraction')

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get all input files
    input_files = sorted(input_dir.glob('*.jsonl'))

    if not input_files:
        print(f"ERROR: No .jsonl files in {input_dir}")
        return

    print(f"{'=' * 70}")
    print(f"ULTRA-FAST WORDPRESS CLEANER")
    print(f"{'=' * 70}")
    print(f"Files: {len(input_files)}")
    print(f"Workers: {args.workers} cores")
    print(f"Batch size: {args.batch_size}")
    print(f"{'=' * 70}\n")

    total_stats = defaultdict(int)
    start_time = time.time()

    # Process files sequentially (each file uses all cores)
    for input_file in input_files:
        output_file = output_dir / f"{input_file.stem}_cleaned.jsonl"

        file_stats = process_file(
            input_file,
            output_file,
            args.domain_mapping,
            args.workers,
            args.batch_size,
            args.noise_config
        )

        for key, value in file_stats.items():
            total_stats[key] += value

    # Final summary
    total_time = time.time() - start_time
    overall_speed = total_stats['total'] / total_time if total_time > 0 else 0

    print(f"\n{'=' * 70}")
    print(f"FINAL SUMMARY")
    print(f"{'=' * 70}")
    print(f"Total Records:    {total_stats['total']:,}")
    print(f"Success:          {total_stats['success']:,}")
    print(f"Filtered:         {total_stats['filtered']:,}")
    print(f"Duplicates:       {total_stats['duplicate']:,}")
    print(f"Failed:           {total_stats['failed']:,}")
    print(f"Total Time:       {total_time:.1f}s")
    print(f"Overall Speed:    {overall_speed:.0f} records/second")
    print(f"{'=' * 70}\n")


if __name__ == '__main__':
    main()