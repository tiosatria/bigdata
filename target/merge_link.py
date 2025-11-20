#!/usr/bin/env python3
"""
Script to merge multiple text files, deduplicate URLs, and normalize domain names.
"""

import argparse
import re
import sys
from pathlib import Path
from urllib.parse import urlparse


def normalize_url(url):
    """
    Normalize URL by removing www. and keeping only the domain name.

    Args:
        url: URL string to normalize

    Returns:
        Normalized domain name or original string if not a valid URL
    """
    url = url.strip()
    if not url:
        return None

    # Add scheme if missing for proper parsing
    if not url.startswith(('http://', 'https://', '//')):
        url = 'http://' + url

    try:
        parsed = urlparse(url)
        domain = parsed.netloc or parsed.path.split('/')[0]

        # Remove www. prefix
        if domain.startswith('www.'):
            domain = domain[4:]

        return domain if domain else None
    except Exception:
        # If parsing fails, try simple string manipulation
        url = url.replace('http://', '').replace('https://', '').replace('//', '')
        url = url.split('/')[0]  # Get domain part only
        if url.startswith('www.'):
            url = url[4:]
        return url if url else None


def should_filter(url, filter_patterns):
    """
    Check if URL matches any filter pattern.

    Args:
        url: URL string to check
        filter_patterns: List of regex patterns

    Returns:
        True if URL should be filtered out, False otherwise
    """
    if not filter_patterns:
        return False

    for pattern in filter_patterns:
        try:
            if re.search(pattern, url, re.IGNORECASE):
                return True
        except re.error as e:
            print(f"Warning: Invalid regex pattern '{pattern}': {e}", file=sys.stderr)

    return False


def merge_files(folder_path, output_path, dedupe=True, filter_patterns=None):
    """
    Merge text files from a folder, deduplicate and normalize URLs.

    Args:
        folder_path: Path to folder containing text files
        output_path: Path to output file
        dedupe: Whether to deduplicate URLs
        filter_patterns: List of regex patterns to filter out
    """
    folder = Path(folder_path)

    if not folder.exists():
        print(f"Error: Folder '{folder_path}' does not exist", file=sys.stderr)
        sys.exit(1)

    if not folder.is_dir():
        print(f"Error: '{folder_path}' is not a directory", file=sys.stderr)
        sys.exit(1)

    # Find all text files
    text_files = list(folder.glob('*.txt'))

    if not text_files:
        print(f"Warning: No .txt files found in '{folder_path}'", file=sys.stderr)
        sys.exit(1)

    print(f"Found {len(text_files)} text file(s)")

    urls = [] if not dedupe else set()
    processed_count = 0
    filtered_count = 0

    # Process each file
    for file_path in text_files:
        print(f"Processing: {file_path.name}")
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                for line in f:
                    normalized = normalize_url(line)
                    if normalized:
                        processed_count += 1

                        # Apply filters
                        if should_filter(normalized, filter_patterns):
                            filtered_count += 1
                            continue

                        if dedupe:
                            urls.add(normalized)
                        else:
                            urls.append(normalized)
        except Exception as e:
            print(f"Error reading {file_path.name}: {e}", file=sys.stderr)
            continue

    # Write output
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            if dedupe:
                for url in sorted(urls):
                    f.write(url + '\n')
            else:
                for url in urls:
                    f.write(url + '\n')

        final_count = len(urls)
        print(f"\nProcessed {processed_count} URL(s)")
        if filtered_count > 0:
            print(f"Filtered out {filtered_count} URL(s)")
        if dedupe:
            print(f"Unique URLs: {final_count}")
        print(f"Output written to: {output_path}")

    except Exception as e:
        print(f"Error writing output file: {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='Merge multiple text files, deduplicate URLs, and normalize domain names.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  python merge_link.py /path/to/folder
  python merge_link.py /path/to/folder output.txt
  python merge_link.py /path/to/folder --no-dedupe
  python merge_link.py /path/to/folder --filter "example\\.com" "test"
        '''
    )

    parser.add_argument(
        'folder',
        help='Path to folder containing text files'
    )

    parser.add_argument(
        'output',
        nargs='?',
        default='merged.txt',
        help='Output file path (default: merged.txt)'
    )

    parser.add_argument(
        '--no-dedupe',
        action='store_true',
        help='Disable deduplication'
    )

    parser.add_argument(
        '--filter',
        nargs='+',
        metavar='PATTERN',
        help='Filter out URLs matching regex pattern(s)'
    )

    args = parser.parse_args()

    merge_files(
        args.folder,
        args.output,
        dedupe=not args.no_dedupe,
        filter_patterns=args.filter
    )


if __name__ == '__main__':
    main()