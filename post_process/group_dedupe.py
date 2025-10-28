#!/usr/bin/env python3
"""
High-performance JSON/JSONL deduplication and domain grouping tool.
Optimized for large files with parallel processing, memory efficiency, and progress feedback.
Supports nested URL key paths (e.g., 'url', 'meta.url', 'request.meta.url').
"""

import argparse
import json
import os
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Dict, List, Set, Tuple, Optional, Any
import multiprocessing as mp
from tqdm import tqdm


class GroupAndDedupe:
    """
    Deduplicates URLs and optionally groups them by domain.
    Can also deduplicate against external URL lists or other JSON/JSONL files.
    """

    def __init__(self,
                 input_file: str,
                 output_dir: str,
                 url_key: str,
                 group_by_domain: bool,
                 num_workers: int = None,
                 sample_url_file: Optional[str] = None,
                 aggregate_file: Optional[str] = None,
                 aggregate_file_url_key: Optional[str] = None):
        self.input_file = Path(input_file)
        self.output_dir = Path(output_dir)
        self.url_key = url_key
        self.url_key_path = url_key.split('.')  # Support nested keys
        self.group_by_domain = group_by_domain
        self.num_workers = num_workers or max(1, mp.cpu_count() - 2)
        self.chunk_size = 1000

        # Optional external files for deduplication
        self.sample_url_file = Path(sample_url_file) if sample_url_file else None
        self.aggregate_file = Path(aggregate_file) if aggregate_file else None
        self.aggregate_file_url_key = aggregate_file_url_key
        self.aggregate_file_url_key_path = aggregate_file_url_key.split('.') if aggregate_file_url_key else None

        self.output_dir.mkdir(parents=True, exist_ok=True)

    def _get_nested_value(self, obj: Any, key_path: List[str]) -> Optional[str]:
        """
        Safely retrieve a nested value from a dictionary using a key path.

        Args:
            obj: The object to traverse
            key_path: List of keys to traverse (e.g., ['meta', 'url'])

        Returns:
            The value at the nested path, or None if not found
        """
        try:
            current = obj
            for key in key_path:
                if isinstance(current, dict):
                    current = current.get(key)
                    if current is None:
                        return None
                else:
                    return None

            # Ensure we return a string and strip whitespace
            if isinstance(current, str):
                return current.strip()
            elif current is not None:
                return str(current).strip()
            return None
        except (KeyError, TypeError, AttributeError):
            return None

    def _load_external_urls(self) -> Set[str]:
        """Loads URLs from external files to be used for deduplication."""
        external_urls = set()

        if self.sample_url_file:
            print(f"Loading external URLs from sample file: {self.sample_url_file}")
            try:
                if not self.sample_url_file.exists():
                    print(f"Warning: Sample URL file not found: {self.sample_url_file}", file=sys.stderr)
                    return external_urls

                with self.sample_url_file.open('r', encoding='utf-8', errors='ignore') as f:
                    for line_num, line in enumerate(f, 1):
                        url = line.strip()
                        if url and not url.startswith('#'):  # Skip empty lines and comments
                            external_urls.add(url)
                print(f"  Loaded {len(external_urls):,} URLs from sample file.")
            except Exception as e:
                print(f"Warning: Could not read sample URL file: {e}", file=sys.stderr)

        if self.aggregate_file and self.aggregate_file_url_key_path:
            print(f"Loading external URLs from aggregate file: {self.aggregate_file}")
            print(f"  Using URL key: '{self.aggregate_file_url_key}'")

            if not self.aggregate_file.exists():
                print(f"Warning: Aggregate file not found: {self.aggregate_file}", file=sys.stderr)
                return external_urls

            initial_count = len(external_urls)
            try:
                is_jsonl = self.aggregate_file.suffix.lower() == '.jsonl'
                with self.aggregate_file.open('r', encoding='utf-8', errors='ignore') as f:
                    if is_jsonl:
                        for i, line in enumerate(f, 1):
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                record = json.loads(line)
                                url = self._get_nested_value(record, self.aggregate_file_url_key_path)
                                if url:
                                    external_urls.add(url)
                            except json.JSONDecodeError:
                                print(f"Warning: Skipping invalid JSON at line {i} in aggregate file.",
                                      file=sys.stderr)
                    else:
                        data = json.load(f)
                        if isinstance(data, list):
                            for idx, record in enumerate(data):
                                if isinstance(record, dict):
                                    url = self._get_nested_value(record, self.aggregate_file_url_key_path)
                                    if url:
                                        external_urls.add(url)
                        else:
                            print(f"Warning: Aggregate JSON file must contain an array", file=sys.stderr)

                print(f"  Loaded {len(external_urls) - initial_count:,} new URLs from aggregate file.")
            except Exception as e:
                print(f"Warning: Could not read aggregate file: {e}", file=sys.stderr)

        return external_urls

    def extract_domain(self, url: str) -> str:
        """
        Extract main domain from URL.

        Args:
            url: The URL string to parse

        Returns:
            Sanitized domain name suitable for use as a filename
        """
        if not url or not isinstance(url, str):
            return 'invalid'

        try:
            # Handle URLs without scheme
            if not url.startswith(('http://', 'https://', '//')):
                url = 'http://' + url

            parsed = urlparse(url)
            domain = parsed.netloc or parsed.path.split('/')[0]

            # Remove www prefix
            if domain.startswith('www.'):
                domain = domain[4:]

            # Remove port number
            if ':' in domain:
                domain = domain.split(':')[0]

            # Sanitize for filesystem
            domain = domain.replace('/', '_').replace('\\', '_').replace(':', '_')

            return domain if domain else 'unknown'
        except Exception:
            return 'invalid'

    def read_chunks(self) -> List[List[dict]]:
        """Read input file in chunks with progress feedback."""
        if not self.input_file.exists():
            raise FileNotFoundError(f"Input file not found: {self.input_file}")

        chunks, current_chunk = [], []
        is_jsonl = self.input_file.suffix.lower() == '.jsonl'
        print(f"\nReading {self.input_file}...")

        try:
            with open(self.input_file, 'r', encoding='utf-8', errors='ignore') as f:
                if is_jsonl:
                    # Count total lines for progress bar
                    print("  Counting lines...")
                    total_lines = sum(1 for _ in open(self.input_file, 'r', encoding='utf-8', errors='ignore'))

                    pbar = tqdm(f, total=total_lines, desc=f"Reading {self.input_file.name}", unit=" lines")
                    for i, line in enumerate(pbar, 1):
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            if isinstance(record, dict):
                                current_chunk.append(record)
                                if len(current_chunk) >= self.chunk_size:
                                    chunks.append(current_chunk)
                                    current_chunk = []
                            else:
                                tqdm.write(f"Warning: Skipping non-dict record at line {i}", file=sys.stderr)
                        except json.JSONDecodeError as e:
                            tqdm.write(f"Warning: Skipping invalid JSON at line {i}: {e}", file=sys.stderr)
                    pbar.close()
                else:
                    print(f"  Loading {self.input_file.name} into memory...")
                    data = json.load(f)
                    if not isinstance(data, list):
                        raise ValueError("JSON file must contain an array of objects")

                    for i in tqdm(range(0, len(data), self.chunk_size), desc="Creating chunks"):
                        chunk = data[i:i + self.chunk_size]
                        # Filter out non-dict items
                        chunk = [item for item in chunk if isinstance(item, dict)]
                        if chunk:
                            chunks.append(chunk)

                if current_chunk:
                    chunks.append(current_chunk)

        except json.JSONDecodeError as e:
            print(f"Error: Invalid JSON format in input file: {e}", file=sys.stderr)
            raise
        except Exception as e:
            print(f"Error reading input file: {e}", file=sys.stderr)
            raise

        print(f"Total chunks created: {len(chunks)}")
        return chunks

    def process_chunk(self, chunk: List[dict]) -> Tuple[Dict[str, List[dict]], Set[str], int]:
        """
        Process a chunk: extract domains and track seen URLs within the chunk.

        Returns:
            Tuple of (domain_records, seen_urls_in_chunk, skipped_count)
        """
        domain_records = defaultdict(list)
        seen_urls_in_chunk = set()
        skipped_count = 0

        for record in chunk:
            if not isinstance(record, dict):
                skipped_count += 1
                continue

            url = self._get_nested_value(record, self.url_key_path)

            if not url:
                skipped_count += 1
                continue

            if url in seen_urls_in_chunk:
                continue

            seen_urls_in_chunk.add(url)
            domain = self.extract_domain(url)
            domain_records[domain].append(record)

        return dict(domain_records), seen_urls_in_chunk, skipped_count

    def dedupe_and_group(self):
        """Main processing function with parallel execution."""
        mode = "grouping and deduplication" if self.group_by_domain else "deduplication"
        print(f"\n{'=' * 60}")
        print(f"Starting {mode}")
        print(f"Workers: {self.num_workers}")
        print(f"URL key: '{self.url_key}'")
        print(f"{'=' * 60}")

        global_seen_urls = self._load_external_urls()
        if global_seen_urls:
            print(f"Starting with {len(global_seen_urls):,} pre-loaded unique URLs to filter against.")

        chunks = self.read_chunks()
        if not chunks:
            print("No data to process!")
            return

        if self.group_by_domain:
            all_domain_records = defaultdict(list)
        else:
            all_unique_records = []

        total_skipped = 0
        total_duplicates = 0

        with ProcessPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {executor.submit(self.process_chunk, chunk): i for i, chunk in enumerate(chunks)}
            pbar = tqdm(as_completed(futures), total=len(chunks), desc="Processing chunks")

            for future in pbar:
                chunk_idx = futures[future]
                try:
                    domain_records, chunk_urls, skipped = future.result()
                    total_skipped += skipped

                    for domain, records in domain_records.items():
                        for record in records:
                            url = self._get_nested_value(record, self.url_key_path)
                            if url and url not in global_seen_urls:
                                global_seen_urls.add(url)
                                if self.group_by_domain:
                                    all_domain_records[domain].append(record)
                                else:
                                    all_unique_records.append(record)
                            elif url:
                                total_duplicates += 1

                except Exception as e:
                    tqdm.write(f"Error processing chunk {chunk_idx}: {e}", file=sys.stderr)

            pbar.close()

        print(f"\nWriting results to {self.output_dir}")
        total_records = 0

        if self.group_by_domain:
            for domain, records in tqdm(sorted(all_domain_records.items()), desc="Writing grouped files"):
                output_file = self.output_dir / f"{domain}.jsonl"
                with open(output_file, 'w', encoding='utf-8', errors='ignore') as f:
                    for record in records:
                        f.write(json.dumps(record, ensure_ascii=False) + '\n')
                total_records += len(records)

            print(f"\n{'=' * 60}\nGrouping and deduplication complete!")
            print(f"Total unique URLs written: {total_records:,}")
            print(f"Total domains: {len(all_domain_records):,}")
            print(f"Duplicates filtered: {total_duplicates:,}")
            print(f"Records skipped (missing/invalid URL): {total_skipped:,}")
        else:
            output_filename = f"{self.input_file.stem}_deduped.jsonl"
            output_file = self.output_dir / output_filename

            with open(output_file, 'w', encoding='utf-8', errors='ignore') as f:
                for record in tqdm(all_unique_records, desc=f"Writing {output_filename}", unit=" records"):
                    f.write(json.dumps(record, ensure_ascii=False) + '\n')

            total_records = len(all_unique_records)
            print(f"\n{'=' * 60}\nDeduplication complete!")
            print(f"Total unique URLs written: {total_records:,}")
            print(f"Duplicates filtered: {total_duplicates:,}")
            print(f"Records skipped (missing/invalid URL): {total_skipped:,}")

        print(f"Output directory: {self.output_dir}\n{'=' * 60}")


def main():
    parser = argparse.ArgumentParser(
        description='Deduplicate and group JSON/JSONL by domain with high throughput.',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Deduplicate with top-level URL key
  %(prog)s --input data.jsonl --output-dir output --url-key url

  # Use nested URL key
  %(prog)s --input data.jsonl --output-dir output --url-key meta.url

  # Use deeply nested URL key
  %(prog)s --input data.jsonl --output-dir output --url-key request.meta.url

  # Group by domain into multiple files
  %(prog)s --input data.json --output-dir results --url-key url --group

  # Deduplicate against a simple list of URLs in a text file
  %(prog)s --input new_data.jsonl --output-dir deduped --url-key url --sample-url seen_urls.txt

  # Deduplicate against another JSONL file with nested key
  %(prog)s --input new_data.jsonl --output-dir deduped --url-key url \\
           --aggregate-file old_data.jsonl --aggregate-file-url-key response.url

  # All options combined
  %(prog)s --input data.json --output-dir final --url-key meta.url --group \\
           --workers 16 --sample-url blocklist.txt
        """
    )
    parser.add_argument('--input', required=True,
                        help='Input JSON or JSONL file')
    parser.add_argument('--output-dir', required=True,
                        help='Output directory for resulting file(s)')
    parser.add_argument('--url-key', required=True,
                        help='Key path for the URL field (e.g., "url", "meta.url", "request.meta.url")')
    parser.add_argument('--group', action='store_true',
                        help="Group output by domain. If not specified, a single deduplicated file is created.")
    parser.add_argument('--workers', type=int, default=None,
                        help='Number of parallel workers (default: CPU count - 2)')
    parser.add_argument('--sample-url',
                        help="Path to a text file with URLs (one per line) to deduplicate against.")
    parser.add_argument('--aggregate-file',
                        help="Path to a JSON/JSONL file to deduplicate against.")
    parser.add_argument('--aggregate-file-url-key',
                        help="The key path for the URL in the --aggregate-file (required if --aggregate-file is used).")

    args = parser.parse_args()

    if args.aggregate_file and not args.aggregate_file_url_key:
        parser.error("--aggregate-file-url-key is required when using --aggregate-file")

    try:
        processor = GroupAndDedupe(
            input_file=args.input,
            output_dir=args.output_dir,
            url_key=args.url_key,
            group_by_domain=args.group,
            num_workers=args.workers,
            sample_url_file=args.sample_url,
            aggregate_file=args.aggregate_file,
            aggregate_file_url_key=args.aggregate_file_url_key
        )
        processor.dedupe_and_group()
    except KeyboardInterrupt:
        print("\n\nInterrupted by user", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()