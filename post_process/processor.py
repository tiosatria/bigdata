#!/usr/bin/env python3
"""
Processor: converts raw crawl records (JSON/JSONL) into standardized JSONL records.
- Decoupled from domain configs, fully args-based
- Configurable cleaning pipelines via command-line arguments
- Output schema:
  {
    'id': <uuid4>,
    'text': f"{title}\n{body}",
    'meta': {
      'data_info': {
        'lang': <lang>, 'url': <url>, 'source': <source_domain>, 'type': 'general',
        'processing_date': <timestamp>, 'delivery_version': 'V1', 'title': <title>
      },
      'content_info': {'domain': <source_type>, 'subdomain': <subcat>}
    }
  }
"""
import argparse
import json
import re
import sys
import uuid
from pathlib import Path
from multiprocessing import cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone

import goose3
import trafilatura.external
from bs4 import BeautifulSoup
from tqdm import tqdm

from post_process.jsonloader import JSONLoader

try:
    from trafilatura import extract
    from lxml import html as lxml_html

    TRAFILATURA_AVAILABLE = True
except ImportError:
    TRAFILATURA_AVAILABLE = False
    print("Warning: trafilatura not available. HTML cleaning will be disabled.", file=sys.stderr)


# ---------------
# Cleaner Registry
# ---------------

class CleanerRegistry:
    """Registry for field cleaners"""
    _cleaners = {}

    @classmethod
    def register(cls, name: str):
        """Decorator to register a cleaner"""

        def decorator(func):
            cls._cleaners[name] = func
            return func

        return decorator

    @classmethod
    def get(cls, name: str):
        """Get a cleaner by name"""
        return cls._cleaners.get(name)

    @classmethod
    def list_cleaners(cls):
        """List all available cleaners"""
        return list(cls._cleaners.keys())


# ---------------
# Field Cleaners
# ---------------

@CleanerRegistry.register('strip')
def clean_strip(value: str) -> str:
    """Strip whitespace"""
    return value.strip() if isinstance(value, str) else value


@CleanerRegistry.register('lowercase')
def clean_lowercase(value: str) -> str:
    """Convert to lowercase"""
    return value.lower() if isinstance(value, str) else value


@CleanerRegistry.register('normalize_whitespace')
def clean_normalize_whitespace(value: str) -> str:
    """Normalize whitespace (collapse multiple spaces)"""
    if not isinstance(value, str):
        return value
    return ' '.join(value.split())

@CleanerRegistry.register('remove_html')
def clean_remove_html(value: str) -> str:
    """Remove HTML tags"""
    if not isinstance(value, str):
        return value
    try:
        if TRAFILATURA_AVAILABLE:
            doc = lxml_html.fromstring(value)
            return doc.text_content()
    except Exception:
        pass
    # Fallback: simple regex
    import re
    return re.sub(r'<[^>]+>', '', value)

# ---------------
# HTML Cleaning
# ---------------

from html import unescape

def strip_html(html_str: str) -> str:
    if not html_str:
        return ""
    soup = BeautifulSoup(html_str, "html.parser")
    text = soup.get_text(strip=True)
    return unescape(" ".join(text.split()))

def html_cleaning(
        html_content: str,
        url:str,
        prune_xpath: Optional[List[str]] = None,
        retain_images: bool = False,
        retain_tables: bool = False,
        body_xpath: Optional[str] = None,
        output_format: str = 'txt'
) -> Optional[str]:
    """Clean HTML using trafilatura"""
    if not TRAFILATURA_AVAILABLE:
        return None

    if not html_content or not isinstance(html_content, str):
        return None

    try:
        # Parse HTML and prune specified xpaths
        doc = lxml_html.fromstring(html_content)
        if body_xpath:
            body = doc.xpath(body_xpath)
            if body:
                doc = body[0]
        if prune_xpath:
            try:
                for xpath in prune_xpath:
                    for element in doc.xpath(xpath):
                        element.getparent().remove(element)
            except Exception as e:
                print(f"Warning: XPath pruning failed: {e}", file=sys.stderr)
        # Extract with trafilatura
        html_content = lxml_html.tostring(doc, encoding='unicode')
        result = extract(
            html_content,
            include_images=retain_images,
            include_tables=retain_tables,
            output_format=output_format,
            include_comments=False,
            include_links=False,
            prune_xpath=prune_xpath,
            url=url
        )
        if not result:
            result = strip_html(html_content)
        return result
    except Exception as e:
        print(f"Warning: trafilatura extraction & fallback method has failed: {e}", file=sys.stderr)
        return None

def apply_field_cleaners(value: Any,  cleaner_names: Optional[List[str]]) -> Any:
    """Apply a chain of cleaners to a field value"""
    if not cleaner_names or value is None:
        return value

    result = value
    for cleaner_name in cleaner_names:
        cleaner = CleanerRegistry.get(cleaner_name)
        if cleaner:
            try:
                result = cleaner(result)
            except Exception as e:
                print(f"Warning: cleaner '{cleaner_name}' failed: {e}", file=sys.stderr)

    return result


# ---------------
# Filtering
# ---------------

def should_filter_record(
        record: Dict[str, Any],
        title_filters_containing: Optional[List[str]],
        tags_filters_containing: Optional[List[str]],
        categories_filters_containing: Optional[List[str]],
        url_filters_containing: Optional[List[str]],
        content_filters_containing: Optional[List[str]],
        title_filters_regex: Optional[List[re.Pattern]],
        tags_filters_regex: Optional[List[re.Pattern]],
        categories_filters_regex: Optional[List[re.Pattern]],
        content_filters_regex: Optional[List[re.Pattern]],
        url_filters_regex: Optional[List[re.Pattern]]
) -> tuple[bool, Optional[str]]:
    """
    Check if record should be filtered out.
    Returns (should_filter, reason)
    """
    # Title filter (case-insensitive substring match)
    meta = record.get('meta', {})

    if not meta:
        return True, 'no_meta'

    if title_filters_containing:
        title = (meta.get('title') or '').lower()
        for filter_str in title_filters_containing:
            if filter_str.lower() in title:
                return True, f"title_filter:{filter_str}"
    tags = meta.get('tags', [])
    # Tags filter (check if any tag matches)
    if tags_filters_containing:
        if isinstance(tags, str):
            tags = [tags]
        elif not isinstance(tags, list):
            tags = []

        tags_lower = [str(t).lower() for t in tags]
        for filter_str in tags_filters_containing:
            if filter_str.lower() in tags_lower:
                return True, f"tags_filter:{filter_str}"

    if categories_filters_containing:
        categories = meta.get('content_info', {}).get('categories', [])
        if isinstance(categories, str):
            categories = [categories]
        elif not isinstance(categories, list):
            categories = []

        for filter_str in categories_filters_containing:
            if filter_str.lower() in categories:
                return True, f"categories_filter:{filter_str}"

    if url_filters_containing:
        url = (meta.get('url') or '').lower()
        for filter_str in url_filters_containing:
            if filter_str.lower() in url:
                return True, f"url_filter:{filter_str}"

    if title_filters_regex:
        title = (meta.get('title') or '').lower()
        for pattern in title_filters_regex:
            if pattern.search(title):
                return True, f"title_filter_regex:{pattern.pattern}"

    if tags_filters_regex:
        tags = meta.get('tags', [])
        if isinstance(tags, str):
            tags = [tags]
        elif not isinstance(tags, list):
            tags = []

        for tag in tags:
            for pattern in tags_filters_regex:
                if pattern.search(tag):
                    return True, f"tags_filter_regex:{pattern.pattern}"

    if categories_filters_regex:
        categories = meta.get('categories', [])
        if isinstance(categories, str):
            categories = [categories]
        elif not isinstance(categories, list):
            categories = []

        for category in categories:
            for pattern in categories_filters_regex:
                if pattern.search(category):
                    return True, f"categories_filter_regex:{pattern.pattern}"

    if url_filters_regex:
        url = (meta.get('url') or '').lower()
        for pattern in url_filters_regex:
            if pattern.search(url):
                return True, f"url_filter_regex:{pattern.pattern}"

    if content_filters_regex:
        body = (record.get('body') or '').lower()
        for pattern in content_filters_regex:
            if pattern.search(body):
                return True, f"content_filter_regex:{pattern.pattern}"

    # Content filter (most expensive, check last)
    if content_filters_containing:
        body = (record.get('body') or '').lower()
        for filter_str in content_filters_containing:
            if filter_str.lower() in body:
                return True, f"content_filter:{filter_str}"

    return False, None


# ---------------
# Worker functions
# ---------------

import re


# re.compile(r"(?:\n)?submitted by:\s*.+$", re.IGNORECASE | re.MULTILINE),

END_TEMPLATE_RE = [re.compile(
    r"(?:\n)?(?:"
    r"submitted by|submited by|shared by|courtesy of|"
    r"contributed by|provided by|posted by|written by|"
    r"author:?|credit(?:ed)? to|thanks to|source:?|"
    r"recipe by|photo by|image by"
    r").*",
    re.IGNORECASE | re.DOTALL
)]

def strip_end_template(text: str) -> str:
    for pattern in END_TEMPLATE_RE:
        text = pattern.sub("", text)
    return text.strip()


def _process_record(
        record: Dict[str, Any],
        config: Dict[str, Any]
) -> tuple[Optional[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Process a single record with cleaning and filtering.
    Returns (ok_record, fail_record). Only one of them is non-None.
    """
    if not isinstance(record, dict):
        return None, {
            'reason': 'invalid_record',
            'details': 'not a dict'
        }

    # Apply filtering BEFORE cleaning
    should_filter, filter_reason = should_filter_record(
        record,
        config.get('filter_title_containing'),
        config.get('filter_tags_containing'),
        config.get('filter_categories_containing'),
        config.get('filter_url_containing'),
        config.get('filter_body_containing'),
        config.get('filter_title_regex'),
        config.get('filter_tags_regex'),
        config.get('filter_categories_regex'),
        config.get('filter_body_regex'),
        config.get('filter_url_regex')
    )

    if should_filter:
        return None, {
            'reason': 'filtered',
            'filter_reason': filter_reason,
            'url': record.get('url'),
            'title': record.get('title'),
        }

    # Clean fields based on configuration
    cleaned_record = record.copy()

    # Apply HTML cleaning if specified
    if 'html' in config.get('cleaners', []):
        body_html = cleaned_record.get('body', '')
        if body_html:
            cleaned_body = html_cleaning(
                body_html,
                record.get('meta',{}).get('url'),
                prune_xpath=config.get('prune_xpath'),
                retain_images=config.get('retain_images', False),
                retain_tables=config.get('retain_tables', False),
                output_format=config.get('format', 'txt'),
                body_xpath=config.get('body_xpath')
            )
            if len(cleaned_body):
                cleaned_record['body'] = cleaned_body
            else:
                cleaned_record['body'] = None

    if 'end_template' in config.get('cleaners',[]):
        cleaned_record['body'] = strip_end_template(cleaned_record['body'])

    # Apply field-specific cleaners
    for field, cleaner_key in [
        ('title', 'title_cleaners'),
        ('tags', 'tags_cleaners'),
        ('author', 'author_cleaners'),
        ('date', 'date_cleaners')
    ]:
        if field in cleaned_record:
            cleaners = config.get(cleaner_key)
            if cleaners:
                cleaned_record['meta'][field] = apply_field_cleaners(
                    cleaned_record[field],
                    cleaners
                )

    # Extract required fields
    title = (cleaned_record.get('meta',{}).get('title') or '').strip()

    body = cleaned_record.get('body') or ''

    site_name = config.get('site_name')

    if site_name and config.get('clean_title_template'):
        separator_to_use = None
        separators = ['|']
        for sep in separators:
            if sep in title:
                separator_to_use = sep
                break

        title.split(separator_to_use)
        title = title.split(separator_to_use)[0].strip()

    if not title and not body:
        return None, {
            'reason': 'empty_content',
            'url': record.get('meta',{}).get('url'),
            'title': title,
            'source_domain': record.get('meta',{}).get('hostname',''),
            'lang': record.get('meta',{}).get('language','en'),
            'text_length': 0
        }

    # Build text content
    text = f"{title}\n{body}".strip()
    if len(text) < config.get('min_text_length', 200):
        return None, {
            'reason': 'too_short',
            'url': record.get('meta',{}).get('url'),
            'title': title,
            'source_domain': record.get('meta',{}).get('hostname',''),
            'lang': record.get('meta',{}).get('language','en'),
            'text_length': len(text)
        }

    # Determine timestamp
    if config.get('timestamp_now'):
        timestamp = datetime.now(timezone.utc).isoformat()
    else:
        timestamp = record.get('meta',{}).get('filedate') or record.get('meta',{}).get('date') or datetime.now(timezone.utc).isoformat()
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

    # Extract metadata
    lang = cleaned_record.get('meta',{}).get('language') or 'en'
    url = (cleaned_record.get('meta',{}).get('url') or '').strip()
    source_domain = cleaned_record.get('meta',{}).get('hostname', 'unknown')

    # Infer domain/subdomain from tags
    tags = cleaned_record.get('meta',{}).get('tags',[])
    tag_list: List[str] = []
    if isinstance(tags, list):
        tag_list = [str(t) for t in tags if t is not None]
    elif isinstance(tags, str):
        tag_list = [tags]
    tag_list_clean = [t.strip() for t in tag_list if str(t).strip()]

    def is_home(val: str) -> bool:
        return str(val).strip().lower() == 'home'

    domain_tag = None
    for t in tag_list_clean:
        if not is_home(t):
            domain_tag = t
            break
    subdomain_tag = None
    for t in reversed(tag_list_clean):
        if not is_home(t):
            subdomain_tag = t
            break
    if subdomain_tag and domain_tag and subdomain_tag == domain_tag:
        subdomain_tag = None

    specified_domain = config.get('specify_domain')
    specified_subdomain = config.get('specify_subdomain')

    domain_val = specified_domain or domain_tag or config.get('default_domain', 'general')
    subdomain_val = specified_subdomain or subdomain_tag or config.get('default_subdomain', 'living')
    type_val = config.get('default_type', 'article')

    # Build output record
    out = {
        'id': str(uuid.uuid4()),
        'text': text,
        'meta': {
            'data_info': {
                'lang': lang,
                'url': url,
                'source': source_domain,
                'type': type_val,
                'processing_date': timestamp,
                'delivery_version': 'V1',
                'title': title
            },
            'content_info': {
                'domain': domain_val,
                'subdomain': subdomain_val
            }
        }
    }
    return out, None


def _process_chunk(
        chunk: List[Dict[str, Any]],
        config: Dict[str, Any]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Process a list of records.
    Returns dict with keys 'ok' and 'fail'.
    """
    ok: List[Dict[str, Any]] = []
    fail: List[Dict[str, Any]] = []

    for rec in chunk:
        converted, failed = _process_record(rec, config)
        if converted is not None:
            ok.append(converted)
        elif failed is not None:
            fail.append(failed)

    return {'ok': ok, 'fail': fail}


# ---------------
# Main CLI
# ---------------

def main():
    parser = argparse.ArgumentParser(
        description='Export data to JSONL format with parallel processing.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"""
Available cleaners: {', '.join(CleanerRegistry.list_cleaners())}

Examples:
  # Basic processing with HTML cleaning
  python processor.py -i data.jsonl --cleaners html

  # HTML cleaning with image/table retention
  python processor.py -i data.jsonl --cleaners html --retain-img --retain-tbl

  # Apply cleaners to specific fields
  python processor.py -i data.jsonl --title-cleaners strip normalize_whitespace

  # Filter by title and tags
  python processor.py -i data.jsonl --title-filter "spam" "advertisement" --tags-filter "nsfw"

  # Prune specific elements before cleaning
  python processor.py -i data.jsonl --cleaners html --prune-xpath "//script" "//style"
        """
    )

    # Input/Output
    parser.add_argument('--input', '-i', required=True, help='Input file (JSON or JSONL)')
    parser.add_argument('--output', '-o', type=str, help='Output JSONL file path (auto-generated if not specified)')

    # Processing options
    parser.add_argument('--workers', type=int, default=cpu_count(),
                        help=f'Number of parallel workers (default: {cpu_count()})')
    parser.add_argument('--limit', type=int, help='Limit number of records to process')
    parser.add_argument('--chunk-size', type=int, default=100,
                        help='Records per chunk for parallel processing (default: 100)')
    parser.add_argument('--min-text-length', type=int, default=200,
                        help='Minimum length of combined title+body text (default: 200)')

    # Cleaners
    parser.add_argument('--cleaners', nargs='+', choices=['html', 'end_template'],
                        help='List of cleaners to apply')

    parser.add_argument('--prune-xpath', nargs='+',
                        help='XPath expressions to prune from HTML before cleaning')

    # HTML cleaner options

    parser.add_argument('--retain-img', action='store_true',
                        help='Retain images in trafilatura output')
    parser.add_argument('--retain-tbl', action='store_true',
                        help='Retain tables in trafilatura output')

    parser.add_argument('--format', type=str, default='txt',
                        choices=['text', 'markdown', 'xml'],
                        help='Trafilatura output format (default: text)')

    parser.add_argument('--body-xpath', help='body xpath to target for extraction')

    parser.add_argument('--title-cleaners', nargs='+',
                        choices=CleanerRegistry.list_cleaners(),
                        help='Cleaners to apply to title field')

    parser.add_argument('--author-cleaners', nargs='+',
                        choices=CleanerRegistry.list_cleaners(),
                        help='Cleaners to apply to author field')

    parser.add_argument('--date-cleaners', nargs='+',
                        choices=CleanerRegistry.list_cleaners(),
                        help='Cleaners to apply to date field')

    # Filters
    parser.add_argument('--filter-title-containing', nargs='+',
                        help='Filter out records with titles containing these strings')

    parser.add_argument('--filter-tags-containing', nargs='+',
                        help='Filter out records with tags matching these strings')

    parser.add_argument('--filter-body-containing', nargs='+',
                        help='Filter out records with body containing these strings (expensive)')

    parser.add_argument('--filter-categories-containing', nargs='+',
                        help='Filter out records with categories containing these strings')

    parser.add_argument('--filter-url-containing', nargs='+',
                        help='Filter out url containing these strings')

    parser.add_argument('--filter-title-regex', action='store_true',
                        help='Toggle title filter to use regex instead of containing')

    parser.add_argument('--filter-tags-regex', nargs='+', help='filter out records with tags matching these regex strings')

    parser.add_argument('--filter-body-regex', nargs='+', help='filter out records with body containing these regex strings (expensive)')

    parser.add_argument('--filter-categories-regex', nargs='+', help='filter out records with categories containing these regex strings')

    parser.add_argument('--filter-url-regex', nargs='+', help='filter out url containing these regex strings')

    # Timestamp options
    parser.add_argument('--timestamp-now', action='store_true',
                        help='Use current timestamp for all records instead of crawl timestamp')

    # Domain fallbacks
    parser.add_argument('--default-domain', type=str, default='general',
                        help='Fallback domain value (default: general)')
    parser.add_argument('--default-subdomain', type=str,
                        help='Fallback subdomain value (default: None)')
    parser.add_argument('--default-type', type=str, default='article',
                        help='Fallback type value (default: article)')

    parser.add_argument("--site-name", type=str, help="Site name to use for site template cleanup")

    parser.add_argument('--clean-title-template', action='store_true',
                        help='Clean title template from site name')

    parser.add_argument("--specify-domain", type=str)
    parser.add_argument("--specify-subdomain", type=str)

    args = parser.parse_args()

    title_regexs : list[re.Pattern] = []
    tags_regexs : list[re.Pattern] = []
    body_regexs : list[re.Pattern] = []
    categories_regexs : list[re.Pattern] = []
    url_regexs : list[re.Pattern] = []

    if args.filter_title_regex:
        for reg in args.filter_title_regex:
            title_regexs.append(re.compile(reg))
    if args.filter_tags_regex:
        for reg in args.filter_tags_regex:
            tags_regexs.append(re.compile(reg))
    if args.filter_body_regex:
        for reg in args.filter_body_regex:
            body_regexs.append(re.compile(reg))
    if args.filter_categories_regex:
        for reg in args.filter_categories_regex:
            categories_regexs.append(re.compile(reg))
    if args.filter_url_regex:
        for reg in args.filter_url_regex:
            url_regexs.append(re.compile(reg))

    # Validate input
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Check trafilatura availability if HTML cleaning requested
    if args.cleaners and 'html' in args.cleaners and not TRAFILATURA_AVAILABLE:
        print("Error: HTML cleaner requires trafilatura. Install with: pip install trafilatura", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(f"{input_path.stem}_processed.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Build processing config
    config = {
        'cleaners': args.cleaners or [],
        'prune_xpath': args.prune_xpath,
        'retain_images': args.retain_img,
        'retain_tables': args.retain_tbl,
        'format': args.format,
        'title_cleaners': args.title_cleaners,
        'author_cleaners': args.author_cleaners,
        'date_cleaners': args.date_cleaners,
        'min_text_length': args.min_text_length,
        'timestamp_now': args.timestamp_now,
        'default_domain': args.default_domain,
        'default_subdomain': args.default_subdomain,
        'default_type': args.default_type,
        'body_xpath': args.body_xpath,
        'specify_domain': args.specify_domain,
        'specify_subdomain': args.specify_subdomain,
        'site_name': args.site_name,
        'clean_title_template': args.clean_title_template,
        'filter_title_containing': args.filter_title_containing,
        'filter_tags_containing': args.filter_tags_containing,
        'filter_body_containing': args.filter_body_containing,
        'filter_categories_containing': args.filter_categories_containing,
        'filter_url_containing': args.filter_url_containing,
        'filter_title_regex': title_regexs,
        'filter_tags_regex': tags_regexs,
        'filter_body_regex': body_regexs,
        'filter_categories_regex': categories_regexs,
        'filter_url_regex': url_regexs
    }

    # Initialize JSON loader
    loader = JSONLoader(path=input_path, chunk_size=max(1, args.chunk_size), desc=None)
    try:
        total_count = loader.count()
    except Exception:
        total_count = None

    limit = args.limit if args.limit is not None else total_count

    total_to_process = min(total_count, limit) if (
            total_count is not None and limit is not None) else limit or total_count

    # Print configuration
    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Workers: {args.workers}")
    if args.cleaners:
        print(f"Cleaners: {', '.join(args.cleaners)}")
    if total_to_process is not None:
        print(f"Records to process: {total_to_process:,}")
    print("-" * 50)

    failed_path = input_path.with_name(f"{input_path.stem}_failed.jsonl")

    # Load all chunks
    print("Loading data...")
    all_chunks = list(loader.iter_chunks(limit=limit))
    total_records = sum(len(chunk) for chunk in all_chunks)
    print(f"Loaded {len(all_chunks):,} chunks ({total_records:,} records)")

    written = 0
    failed_count = 0

    with output_path.open('w', encoding='utf-8') as fout:
        ffail = None
        with ProcessPoolExecutor(max_workers=args.workers) as executor:
            # Submit all work
            futures = {
                executor.submit(_process_chunk, chunk, config): len(chunk)
                for chunk in all_chunks
            }

            try:
                # Progress tracking
                with tqdm(total=total_records, desc="Processing", unit=" rec", dynamic_ncols=True) as pbar:
                    for future in as_completed(futures):
                        chunk_size = futures[future]
                        try:
                            results = future.result()
                            ok = results.get('ok', [])
                            fail = results.get('fail', [])

                            # Write results
                            for rec in ok:
                                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                                written += 1

                            for fr in fail:
                                if ffail is None:
                                    ffail = failed_path.open('w', encoding='utf-8')
                                ffail.write(json.dumps(fr, ensure_ascii=False) + "\n")
                                failed_count += 1

                            # Update progress
                            pbar.update(len(ok) + len(fail))
                        except Exception as e:
                            print(f"\nError processing chunk: {e}", file=sys.stderr)
                            pbar.update(chunk_size)

            except KeyboardInterrupt:
                print("\nInterrupted by user, shutting down...", file=sys.stderr)
                executor.shutdown(wait=False, cancel_futures=True)
                raise

        # Close failed file if opened
        if ffail is not None:
            try:
                ffail.close()
            except Exception:
                pass

    # Print final summary
    if failed_count:
        print(
            f"\n✓ Finished. Wrote {written:,} records to {output_path}. Failed/filtered: {failed_count:,} -> {failed_path}")
    else:
        try:
            if failed_path.exists():
                failed_path.unlink()
        except Exception:
            pass
        print(f"\n✓ Finished. Wrote {written:,} records to {output_path}. Failed/filtered: 0")


if __name__ == '__main__':
    main()