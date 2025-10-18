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
import sys
import uuid
from pathlib import Path
from multiprocessing import cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timezone
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

def clean_html_with_trafilatura(
        html_content: str,
        prune_xpath: Optional[List[str]] = None,
        retain_images: bool = False,
        retain_tables: bool = False,
        output_format: str = 'text'
) -> Optional[str]:
    """Clean HTML using trafilatura"""
    if not TRAFILATURA_AVAILABLE:
        return None

    if not html_content or not isinstance(html_content, str):
        return None

    try:
        # Parse HTML and prune specified xpaths
        if prune_xpath:
            try:
                doc = lxml_html.fromstring(html_content)
                for xpath in prune_xpath:
                    for element in doc.xpath(xpath):
                        element.getparent().remove(element)
                html_content = lxml_html.tostring(doc, encoding='unicode')
            except Exception as e:
                print(f"Warning: XPath pruning failed: {e}", file=sys.stderr)

        # Extract with trafilatura
        result = extract(
            html_content,
            include_images=retain_images,
            include_tables=retain_tables,
            output_format=output_format,
            include_comments=False,
            include_links=False
        )

        return result
    except Exception as e:
        print(f"Warning: trafilatura extraction failed: {e}", file=sys.stderr)
        return None


def apply_field_cleaners(value: Any, cleaner_names: Optional[List[str]]) -> Any:
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
        title_filters: Optional[List[str]],
        tags_filters: Optional[List[str]],
        content_filters: Optional[List[str]],
        body_key: str = 'body'
) -> tuple[bool, Optional[str]]:
    """
    Check if record should be filtered out.
    Returns (should_filter, reason)
    """
    # Title filter (case-insensitive substring match)
    if title_filters:
        title = (record.get('title') or '').lower()
        for filter_str in title_filters:
            if filter_str.lower() in title:
                return True, f"title_filter:{filter_str}"

    # Tags filter (check if any tag matches)
    if tags_filters:
        tags = record.get('tags', [])
        if isinstance(tags, str):
            tags = [tags]
        elif not isinstance(tags, list):
            tags = []

        tags_lower = [str(t).lower() for t in tags]
        for filter_str in tags_filters:
            if filter_str.lower() in tags_lower:
                return True, f"tags_filter:{filter_str}"

    # Content filter (most expensive, check last)
    if content_filters:
        body = (record.get(body_key) or '').lower()
        for filter_str in content_filters:
            if filter_str.lower() in body:
                return True, f"content_filter:{filter_str}"

    return False, None


# ---------------
# Worker functions
# ---------------

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
        config.get('title_filters'),
        config.get('tags_filters'),
        config.get('content_filters'),
        config.get('body_key', 'body')
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

    # Determine which body field to use
    body_key = config.get('body_key', 'body')
    if config.get('use_content') and record.get('body_content'):
        body_source = 'body_content'
    else:
        body_source = body_key

    # Apply HTML cleaning if specified
    if 'html' in config.get('cleaners', []):
        body_html = cleaned_record.get(body_source, '')
        if body_html:
            cleaned_body = clean_html_with_trafilatura(
                body_html,
                prune_xpath=config.get('prune_xpath'),
                retain_images=config.get('retain_images', False),
                retain_tables=config.get('retain_tables', False),
                output_format=config.get('format', 'txt')
            )
            if cleaned_body:
                cleaned_record['body'] = cleaned_body
            else:
                # If trafilatura fails, keep original
                cleaned_record['body'] = body_html

    # Apply field-specific cleaners
    for field, cleaner_key in [
        ('title', 'title_cleaners'),
        ('tags', 'tags_cleaners'),
        ('author', 'author_cleaners'),
        ('post_date', 'date_cleaners')
    ]:
        if field in cleaned_record:
            cleaners = config.get(cleaner_key)
            if cleaners:
                cleaned_record[field] = apply_field_cleaners(
                    cleaned_record[field],
                    cleaners
                )

    # Extract required fields
    title = (cleaned_record.get('title') or '').strip()
    body = cleaned_record.get('body') or ''

    if not title and not body:
        return None, {
            'reason': 'empty_content',
            'url': record.get('url'),
            'title': title,
            'source_domain': record.get('source_domain'),
            'lang': record.get('lang'),
            'text_length': 0
        }

    # Build text content
    text = f"{title}\n{body}".strip()
    if len(text) < config.get('min_text_length', 200):
        return None, {
            'reason': 'too_short',
            'url': record.get('url'),
            'title': title,
            'source_domain': record.get('source_domain'),
            'lang': record.get('lang'),
            'text_length': len(text)
        }

    # Determine timestamp
    if config.get('timestamp_now'):
        timestamp = datetime.now(timezone.utc).isoformat()
    else:
        timestamp = record.get('timestamp') or record.get('post_date')
        if not timestamp:
            timestamp = datetime.now(timezone.utc).isoformat()

    # Extract metadata
    lang = cleaned_record.get('lang')
    url = (cleaned_record.get('url') or '').strip()
    source_domain = cleaned_record.get('source_domain')

    # Infer domain/subdomain from tags
    tags = cleaned_record.get('tags')
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

    domain_val = domain_tag or config.get('default_domain', 'general')
    subdomain_val = subdomain_tag or config.get('default_subdomain', '')
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
    parser.add_argument('--chunk-size', type=int, default=1000,
                        help='Records per chunk for parallel processing (default: 1000)')
    parser.add_argument('--min-text-length', type=int, default=200,
                        help='Minimum length of combined title+body text (default: 200)')

    # Cleaners
    parser.add_argument('--cleaners', nargs='+', choices=['html'],
                        help='List of cleaners to apply')
    parser.add_argument('--use-content', action='store_true',
                        help='Use body_content field if available, fallback to body')

    # HTML cleaner options
    parser.add_argument('--prune-xpath', nargs='+',
                        help='XPath expressions to prune from HTML before cleaning')
    parser.add_argument('--retain-img', action='store_true',
                        help='Retain images in trafilatura output')
    parser.add_argument('--retain-tbl', action='store_true',
                        help='Retain tables in trafilatura output')
    parser.add_argument('--format', type=str, default='txt',
                        choices=['text', 'markdown', 'xml'],
                        help='Trafilatura output format (default: text)')

    # Field-specific cleaners
    parser.add_argument('--title-cleaners', nargs='+',
                        choices=CleanerRegistry.list_cleaners(),
                        help='Cleaners to apply to title field')
    parser.add_argument('--tags-cleaners', nargs='+',
                        choices=CleanerRegistry.list_cleaners(),
                        help='Cleaners to apply to tags field')
    parser.add_argument('--author-cleaners', nargs='+',
                        choices=CleanerRegistry.list_cleaners(),
                        help='Cleaners to apply to author field')
    parser.add_argument('--date-cleaners', nargs='+',
                        choices=CleanerRegistry.list_cleaners(),
                        help='Cleaners to apply to date field')

    # Filters
    parser.add_argument('--title-filter', nargs='+',
                        help='Filter out records with titles containing these strings')
    parser.add_argument('--tags-filter', nargs='+',
                        help='Filter out records with tags matching these strings')
    parser.add_argument('--content-filter', nargs='+',
                        help='Filter out records with body containing these strings (expensive)')

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

    args = parser.parse_args()

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
        'use_content': args.use_content,
        'body_key': 'body',
        'prune_xpath': args.prune_xpath,
        'retain_images': args.retain_img,
        'retain_tables': args.retain_tbl,
        'format': args.format,
        'title_cleaners': args.title_cleaners,
        'tags_cleaners': args.tags_cleaners,
        'author_cleaners': args.author_cleaners,
        'date_cleaners': args.date_cleaners,
        'title_filters': args.title_filter,
        'tags_filters': args.tags_filter,
        'content_filters': args.content_filter,
        'min_text_length': args.min_text_length,
        'timestamp_now': args.timestamp_now,
        'default_domain': args.default_domain,
        'default_subdomain': args.default_subdomain,
        'default_type': args.default_type
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