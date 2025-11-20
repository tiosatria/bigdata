#!/usr/bin/env python3
"""
High-performance JSONL filtering script for WordPress posts.
Supports parallel processing with multiple filter types.
"""

import argparse
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed
from multiprocessing import cpu_count
import sys

try:
    from tqdm import tqdm
except ImportError:
    print("Error: tqdm is required. Install with: pip install tqdm")
    sys.exit(1)


class FilterConfig:
    """Holds all compiled filter patterns and configurations."""

    def __init__(self, args):
        # URL filters - treat as regex patterns
        self.include_url = self._compile_patterns(args.include_url)
        self.exclude_url = self._compile_patterns(args.exclude_url)

        # Title filters
        self.include_title_re = self._compile_patterns(args.include_title_re)
        self.exclude_title_re = self._compile_patterns(args.exclude_title_re)
        self.include_title_contains = self._parse_list(args.include_title_contains)
        self.exclude_title_contains = self._parse_list(args.exclude_title_contains)

        # Category filters (exact match)
        self.include_category = self._parse_list(args.include_category)
        self.exclude_category = self._parse_list(args.exclude_category)

        # Tag filters (exact match)
        self.include_tag = self._parse_list(args.include_tag)
        self.exclude_tag = self._parse_list(args.exclude_tag)

        self.output_excluded = args.output_excluded

    @staticmethod
    def _compile_patterns(pattern_str: Optional[str]) -> List[re.Pattern]:
        """Compile regex patterns from comma-separated string."""
        if not pattern_str:
            return []
        patterns = [p.strip() for p in pattern_str.split(',') if p.strip()]
        try:
            return [re.compile(p) for p in patterns]
        except re.error as e:
            print(f"Error compiling regex pattern: {e}")
            sys.exit(1)

    @staticmethod
    def _parse_list(list_str: Optional[str]) -> Set[str]:
        """Parse comma-separated values into a set."""
        if not list_str:
            return set()
        return {item.strip() for item in list_str.split(',') if item.strip()}


def match_any_pattern(text: str, patterns: List[re.Pattern]) -> bool:
    """Check if text matches any of the regex patterns."""
    if not text:
        return False
    return any(pattern.search(text) for pattern in patterns)


def contains_any(text: str, items: Set[str]) -> bool:
    """Check if text contains any of the specified items (case-insensitive)."""
    if not text:
        return False
    text_lower = text.lower()
    return any(item.lower() in text_lower for item in items)


def match_any_in_list(values, target_set: Set[str]) -> bool:
    """Check if any value in the list matches target set (converts to string)."""
    if not values or not target_set:
        return False

    # Handle both list and single values
    if not isinstance(values, list):
        values = [values]

    return any(str(v) in target_set for v in values)


def should_include_record(record: Dict, config: FilterConfig) -> Tuple[bool, str]:
    """
    Determine if a record should be included based on filters.
    Returns (should_include, reason_for_exclusion).
    """
    try:
        # Parse body string to JSON
        body_str = record.get('body', '{}')
        if isinstance(body_str, str):
            body = json.loads(body_str)
        else:
            body = body_str

        # URL can be in record.url OR body.link
        url = record.get('url', '') or body.get('link', '')

        # Extract fields with safe navigation
        title = ''
        if 'title' in body and isinstance(body['title'], dict):
            title = body['title'].get('rendered', '')

        # Categories and tags are at body level, NOT in meta
        category = body.get('categories', [])
        tags = body.get('tags', [])

        # Ensure category and tags are lists
        if not isinstance(category, list):
            category = [category] if category else []
        if not isinstance(tags, list):
            tags = [tags] if tags else []

        # Debug: Print first record to verify parsing
        # Uncomment to debug
        # print(f"\nDEBUG - URL: {url}")
        # print(f"DEBUG - Title: {title}")
        # print(f"DEBUG - Category: {category}")
        # print(f"DEBUG - Tags: {tags}")

        # EXCLUDE filters (these take precedence)
        if config.exclude_url and match_any_pattern(url, config.exclude_url):
            return False, "excluded_url"

        if config.exclude_title_re and match_any_pattern(title, config.exclude_title_re):
            return False, "excluded_title_re"

        if config.exclude_title_contains and contains_any(title, config.exclude_title_contains):
            return False, "excluded_title_contains"

        if config.exclude_category and match_any_in_list(category, config.exclude_category):
            return False, "excluded_category"

        if config.exclude_tag and match_any_in_list(tags, config.exclude_tag):
            return False, "excluded_tag"

        # INCLUDE filters (only check if any include filter is set)
        has_include_filters = any([
            config.include_url,
            config.include_title_re,
            config.include_title_contains,
            config.include_category,
            config.include_tag
        ])

        if not has_include_filters:
            return True, ""  # No include filters, pass everything not excluded

        # Check each include filter - ANY match passes
        if config.include_url and match_any_pattern(url, config.include_url):
            return True, ""

        if config.include_title_re and match_any_pattern(title, config.include_title_re):
            return True, ""

        if config.include_title_contains and contains_any(title, config.include_title_contains):
            return True, ""

        if config.include_category and match_any_in_list(category, config.include_category):
            return True, ""

        if config.include_tag and match_any_in_list(tags, config.include_tag):
            return True, ""

        # No include filters matched
        return False, "not_matched_include_filters"

    except (json.JSONDecodeError, KeyError) as e:
        return False, f"parse_error: {str(e)}"
    except Exception as e:
        return False, f"error: {str(e)}"


def process_chunk(args):
    """Process a chunk of lines from the file."""
    lines, config = args
    results = {'included': [], 'excluded': [], 'errors': 0}

    for line in lines:
        line = line.strip()
        if not line:
            continue

        try:
            record = json.loads(line)
            should_include, reason = should_include_record(record, config)

            if should_include:
                results['included'].append(line)
            else:
                results['excluded'].append(line)
        except Exception:
            results['errors'] += 1

    return results


def process_file(file_path: Path, config: FilterConfig, max_workers: Optional[int] = None) -> Dict:
    """Process a single JSONL file and return statistics."""
    output_path = file_path.parent / f"{file_path.stem}_filtered{file_path.suffix}"
    excluded_path = file_path.parent / f"{file_path.stem}_excluded{file_path.suffix}"

    stats = {
        'file': file_path.name,
        'total': 0,
        'included': 0,
        'excluded': 0,
        'errors': 0,
        'error_details': []
    }

    try:
        # Count total lines for progress bar
        with open(file_path, 'r', encoding='utf-8') as f:
            total_lines = sum(1 for _ in f)

        stats['total'] = total_lines

        # Open files with proper context management
        with open(file_path, 'r', encoding='utf-8') as infile, \
                open(output_path, 'w', encoding='utf-8') as outfile:

            # Open excluded file separately if needed
            excfile = open(excluded_path, 'w', encoding='utf-8') if config.output_excluded else None

            try:
                line_num = 0

                for line in tqdm(infile, total=total_lines, desc=f"Processing {file_path.name}",
                                 unit='records'):
                    line_num += 1
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        record = json.loads(line)
                        should_include, reason = should_include_record(record, config)

                        if should_include:
                            outfile.write(line + '\n')
                            stats['included'] += 1
                        else:
                            stats['excluded'] += 1
                            if excfile:
                                excfile.write(line + '\n')

                    except json.JSONDecodeError as e:
                        stats['errors'] += 1
                        if stats['errors'] <= 5:  # Only store first 5 errors
                            stats['error_details'].append(f"Line {line_num}: JSON decode error")
                    except Exception as e:
                        stats['errors'] += 1
                        if stats['errors'] <= 5:
                            stats['error_details'].append(f"Line {line_num}: {str(e)}")

            finally:
                if excfile:
                    excfile.close()

        # Remove output file if empty
        if stats['included'] == 0:
            output_path.unlink()

        # Remove excluded file if empty or not requested
        if config.output_excluded and stats['excluded'] == 0 and excluded_path.exists():
            excluded_path.unlink()

    except Exception as e:
        stats['error_msg'] = str(e)

    return stats


def process_directory(dir_path: Path, config: FilterConfig, max_workers: Optional[int] = None):
    """Process all JSONL files in a directory using parallel processing."""
    jsonl_files = list(dir_path.glob('*.jsonl'))

    if not jsonl_files:
        print(f"No .jsonl files found in {dir_path}")
        return

    if max_workers is None:
        max_workers = max(1, cpu_count() - 1)

    print(f"Found {len(jsonl_files)} JSONL files")
    print(f"Using {max_workers} workers for parallel processing\n")

    all_stats = []

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(process_file, f, config): f for f in jsonl_files}

        with tqdm(total=len(jsonl_files), desc="Overall Progress", unit='files') as pbar:
            for future in as_completed(futures):
                stats = future.result()
                all_stats.append(stats)
                pbar.update(1)

    # Print summary
    print("\n" + "=" * 70)
    print("PROCESSING SUMMARY")
    print("=" * 70)

    total_records = sum(s['total'] for s in all_stats)
    total_included = sum(s['included'] for s in all_stats)
    total_excluded = sum(s['excluded'] for s in all_stats)
    total_errors = sum(s['errors'] for s in all_stats)

    print(f"\nTotal files processed: {len(all_stats)}")
    print(f"Total records: {total_records:,}")
    print(f"Included: {total_included:,} ({total_included / total_records * 100:.1f}%)")
    print(f"Excluded: {total_excluded:,} ({total_excluded / total_records * 100:.1f}%)")
    if total_errors > 0:
        print(f"Errors: {total_errors:,}")

    print("\nPer-file breakdown:")
    print("-" * 70)
    for stats in sorted(all_stats, key=lambda x: x['file']):
        print(f"{stats['file']:40} | "
              f"Total: {stats['total']:6,} | "
              f"Included: {stats['included']:6,} | "
              f"Excluded: {stats['excluded']:6,}")
        if stats.get('error_msg'):
            print(f"  ERROR: {stats['error_msg']}")
        if stats.get('error_details'):
            for err in stats['error_details'][:3]:
                print(f"  {err}")


def main():
    parser = argparse.ArgumentParser(
        description='Filter JSONL records based on WordPress post fields',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Filter single file by URL pattern
  python filter_records.py --file input.jsonl --include-url "guide"

  # Filter directory with multiple criteria (uses all CPU cores)
  python filter_records.py --dir input_dir --include-category 1094,1233 \\
    --exclude-tag 30,49 --include-title-re "(?i)\\bdiy\\b" --output-excluded

  # Complex filtering
  python filter_records.py --file large.jsonl \\
    --include-title-contains "guide,action,do this" \\
    --exclude-title-re "(?i)review|video" \\
    --include-category 1094,1233 --exclude-tag 30,49

Performance Notes:
  - Single file mode: Uses 1 CPU core (sequential processing)
  - Directory mode: Uses all available CPU cores (parallel processing)
  - For very large single files, directory mode on split files is faster

Note: All filters use regex patterns. For simple substring matching:
  - Use plain text: --include-url "guide" 
  - For exact word: --include-title-re "\\bguide\\b"
  - Case insensitive: --include-title-re "(?i)guide"
        """
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--file', type=Path, help='Process a single JSONL file')
    input_group.add_argument('--dir', type=Path, help='Process all JSONL files in directory')

    # Output options
    parser.add_argument('--output-excluded', action='store_true',
                        help='Output excluded records to separate file with _excluded suffix')

    # URL filters
    parser.add_argument('--include-url', help='Include URLs matching regex (comma-separated)')
    parser.add_argument('--exclude-url', help='Exclude URLs matching regex (comma-separated)')

    # Title filters (regex)
    parser.add_argument('--include-title-re', help='Include titles matching regex (comma-separated)')
    parser.add_argument('--exclude-title-re', help='Exclude titles matching regex (comma-separated)')

    # Title filters (contains)
    parser.add_argument('--include-title-contains',
                        help='Include titles containing any of these strings (comma-separated)')
    parser.add_argument('--exclude-title-contains',
                        help='Exclude titles containing any of these strings (comma-separated)')

    # Category filters
    parser.add_argument('--include-category',
                        help='Include records with these category IDs (comma-separated)')
    parser.add_argument('--exclude-category',
                        help='Exclude records with these category IDs (comma-separated)')

    # Tag filters
    parser.add_argument('--include-tag',
                        help='Include records with these tag IDs (comma-separated)')
    parser.add_argument('--exclude-tag',
                        help='Exclude records with these tag IDs (comma-separated)')

    # Performance options
    parser.add_argument('--workers', type=int,
                        help=f'Number of parallel workers (default: {max(1, cpu_count() - 1)})')

    # Debug option
    parser.add_argument('--debug', action='store_true',
                        help='Print first record details for debugging')

    # Verbose option
    parser.add_argument('--verbose', '-v', action='store_true',
                        help='Print detailed processing information')

    args = parser.parse_args()

    # Validate input
    if args.file and not args.file.exists():
        print(f"Error: File not found: {args.file}")
        sys.exit(1)

    if args.dir and not args.dir.exists():
        print(f"Error: Directory not found: {args.dir}")
        sys.exit(1)

    # Create filter configuration
    config = FilterConfig(args)

    # Debug mode - print first record
    if args.debug and args.file:
        print("DEBUG MODE - First record analysis:")
        print("=" * 70)
        try:
            with open(args.file, 'r', encoding='utf-8') as f:
                line = f.readline().strip()
                record = json.loads(line)
                body = json.loads(record.get('body', '{}'))

                print(f"URL: {record.get('url', 'N/A')}")
                print(f"ID: {record.get('id', 'N/A')}")
                print(f"\nBody keys: {list(body.keys())}")

                if 'title' in body:
                    print(f"Title structure: {body['title']}")
                if 'meta' in body:
                    print(f"Meta structure: {body['meta']}")

                should_inc, reason = should_include_record(record, config)
                print(f"\nWould be included: {should_inc}")
                if not should_inc:
                    print(f"Reason: {reason}")

        except Exception as e:
            print(f"Error in debug mode: {e}")
        print("=" * 70 + "\n")
        return

    # Process
    if args.file:
        print(f"Processing single file: {args.file}\n")
        stats = process_file(args.file, config)

        print("\n" + "=" * 70)
        print("PROCESSING COMPLETE")
        print("=" * 70)
        print(f"Total records: {stats['total']:,}")
        if stats['total'] > 0:
            print(f"Included: {stats['included']:,} ({stats['included'] / stats['total'] * 100:.1f}%)")
            print(f"Excluded: {stats['excluded']:,} ({stats['excluded'] / stats['total'] * 100:.1f}%)")
        else:
            print(f"Included: 0 (0.0%)")
            print(f"Excluded: 0 (0.0%)")
        if stats['errors'] > 0:
            print(f"Errors: {stats['errors']:,}")
            for err in stats.get('error_details', [])[:5]:
                print(f"  {err}")

        output_file = args.file.parent / f"{args.file.stem}_filtered{args.file.suffix}"
        if output_file.exists():
            print(f"\nOutput: {output_file}")
        else:
            print(f"\nNo records matched filters. Output file not created.")

        if config.output_excluded:
            excluded_file = args.file.parent / f"{args.file.stem}_excluded{args.file.suffix}"
            if excluded_file.exists():
                print(f"Excluded: {excluded_file}")

    else:  # args.dir
        process_directory(args.dir, config, args.workers)


if __name__ == '__main__':
    main()