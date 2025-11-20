#!/usr/bin/env python3
"""
High-performance file deduplication script with streaming and concurrent processing.
Supports JSONL, JSON, and TXT files with configurable deduplication keys.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Set, Optional, Dict, List, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import re


class DeduplicationStats:
    """Thread-safe statistics tracker."""
    def __init__(self):
        self.lock = threading.Lock()
        self.total_files = 0
        self.processed_files = 0
        self.skipped_files = 0
        self.total_lines = 0
        self.duplicates_removed = 0
        self.errors = 0

    def add_result(self, total: int, duplicates: int, skipped: bool = False):
        with self.lock:
            if skipped:
                self.skipped_files += 1
            else:
                self.processed_files += 1
                self.total_lines += total
                self.duplicates_removed += duplicates

    def add_error(self):
        with self.lock:
            self.errors += 1

    def print_summary(self):
        print("\n" + "="*60)
        print("DEDUPLICATION SUMMARY")
        print("="*60)
        print(f"Total files found:       {self.total_files}")
        print(f"Files processed:         {self.processed_files}")
        print(f"Files skipped:           {self.skipped_files}")
        print(f"Errors:                  {self.errors}")
        print(f"Total lines/records:     {self.total_lines}")
        print(f"Duplicates removed:      {self.duplicates_removed}")
        print(f"Unique lines/records:    {self.total_lines - self.duplicates_removed}")
        print("="*60)


def get_nested_value(data: dict, key_path: str) -> Optional[str]:
    """Extract nested value from dictionary using dot notation."""
    keys = key_path.split('.')
    value = data
    try:
        for key in keys:
            value = value[key]
        return str(value) if value is not None else None
    except (KeyError, TypeError):
        return None


def strip_trailing_number(url: str) -> str:
    """
    Remove trailing numbers from URLs.
    Example: https://site.com/page-2 -> https://site.com/page
    """
    # Match trailing dash/underscore followed by digits at the end
    pattern = r'[-_]\d+/?$'
    return re.sub(pattern, '', url)


def dedupe_txt(input_path: Path, output_path: Path, detect_trailing: bool = False) -> tuple[int, int]:
    """
    Deduplicate text file line by line using streaming.
    Returns (total_lines, duplicates_removed).
    """
    seen: Set[str] = set()
    total = 0
    duplicates = 0

    with open(input_path, 'r', encoding='utf-8', errors='ignore') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        for line in infile:
            total += 1
            stripped = line.strip()
            
            if not stripped:
                continue
            
            # Apply trailing number detection if enabled
            dedup_key = strip_trailing_number(stripped) if detect_trailing else stripped
            
            if dedup_key not in seen:
                seen.add(dedup_key)
                outfile.write(line)
            else:
                duplicates += 1

    return total, duplicates


def dedupe_jsonl(input_path: Path, output_path: Path, key: str, 
                 detect_trailing: bool = False) -> tuple[int, int]:
    """
    Deduplicate JSONL file using streaming.
    Returns (total_lines, duplicates_removed).
    """
    seen: Set[str] = set()
    total = 0
    duplicates = 0

    with open(input_path, 'r', encoding='utf-8', errors='ignore') as infile, \
         open(output_path, 'w', encoding='utf-8') as outfile:
        
        for line in infile:
            total += 1
            stripped = line.strip()
            
            if not stripped:
                continue
            
            try:
                data = json.loads(stripped)
                value = get_nested_value(data, key)
                
                if value is None:
                    continue
                
                # Apply trailing number detection if enabled
                dedup_key = strip_trailing_number(value) if detect_trailing else value
                
                if dedup_key not in seen:
                    seen.add(dedup_key)
                    outfile.write(line)
                else:
                    duplicates += 1
            except json.JSONDecodeError:
                continue

    return total, duplicates


def dedupe_json(input_path: Path, output_path: Path, key: str,
                detect_trailing: bool = False) -> tuple[int, int]:
    """
    Deduplicate JSON file (array of objects).
    Returns (total_records, duplicates_removed).
    """
    with open(input_path, 'r', encoding='utf-8') as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format in {input_path}")

    if not isinstance(data, list):
        raise ValueError(f"JSON file must contain an array of objects: {input_path}")

    seen: Set[str] = set()
    unique_records = []
    total = len(data)
    duplicates = 0

    for record in data:
        if not isinstance(record, dict):
            continue
        
        value = get_nested_value(record, key)
        if value is None:
            continue
        
        # Apply trailing number detection if enabled
        dedup_key = strip_trailing_number(value) if detect_trailing else value
        
        if dedup_key not in seen:
            seen.add(dedup_key)
            unique_records.append(record)
        else:
            duplicates += 1

    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(unique_records, f, ensure_ascii=False, indent=2)

    return total, duplicates


def process_file(file_path: Path, args: argparse.Namespace, stats: DeduplicationStats) -> None:
    """Process a single file with deduplication."""
    ext = file_path.suffix.lower()
    
    # Determine if file should be processed based on extension and filters
    if args.jsonl and ext != '.jsonl':
        return
    if args.json and ext != '.json':
        return
    if args.txt and ext != '.txt':
        return
    
    # Check if key is required but not provided
    if ext in ['.json', '.jsonl'] and not args.key:
        stats.add_result(0, 0, skipped=True)
        return
    
    # Prepare output path
    output_dir = Path(args.out_dir) if args.out_dir else file_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    postfix = args.postfix if args.postfix else '_deduped'
    output_name = f"{file_path.stem}{postfix}{file_path.suffix}"
    output_path = output_dir / output_name
    
    try:
        print(f"Processing: {file_path}")
        
        if ext == '.txt':
            total, duplicates = dedupe_txt(file_path, output_path, args.detect_trailing_url)
        elif ext == '.jsonl':
            total, duplicates = dedupe_jsonl(file_path, output_path, args.key, 
                                            args.detect_trailing_url)
        elif ext == '.json':
            total, duplicates = dedupe_json(file_path, output_path, args.key,
                                           args.detect_trailing_url)
        else:
            stats.add_result(0, 0, skipped=True)
            return
        
        print(f"  ✓ Completed: {total - duplicates}/{total} unique records → {output_path}")
        stats.add_result(total, duplicates)
        
    except Exception as e:
        print(f"  ✗ Error processing {file_path}: {str(e)}", file=sys.stderr)
        stats.add_error()


def find_files(input_path: Path, args: argparse.Namespace) -> List[Path]:
    """Find all files to process based on input path and filters."""
    files = []
    
    if input_path.is_file():
        files.append(input_path)
    elif input_path.is_dir():
        # Determine which extensions to include
        extensions = []
        if args.jsonl:
            extensions.append('.jsonl')
        if args.json:
            extensions.append('.json')
        if args.txt:
            extensions.append('.txt')
        
        # If no specific filter, include all supported formats
        if not extensions:
            # But skip json/jsonl if no key provided
            if args.key:
                extensions = ['.jsonl', '.json', '.txt']
            else:
                extensions = ['.txt']
        
        # Recursively find all matching files
        for ext in extensions:
            files.extend(input_path.rglob(f"*{ext}"))
    
    return sorted(files)


def main():
    parser = argparse.ArgumentParser(
        description='High-performance file deduplication with streaming and concurrency',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python deduper.py file.jsonl --key url
  python deduper.py file.txt
  python deduper.py input/dir --jsonl --key url
  python deduper.py input/dir
  python deduper.py input/dir --key meta.data_info.url
  python deduper.py file.jsonl --key url --detect-trailing-url
  python deduper.py input/dir --key url --out-dir output/
        """
    )
    
    parser.add_argument('input', type=str, help='Input file or directory')
    parser.add_argument('--key', type=str, help='Key for JSON/JSONL deduplication (supports nested keys with dot notation)')
    parser.add_argument('--jsonl', action='store_true', help='Process only JSONL files in directory')
    parser.add_argument('--json', action='store_true', help='Process only JSON files in directory')
    parser.add_argument('--txt', action='store_true', help='Process only TXT files in directory')
    parser.add_argument('--postfix', type=str, help='Custom output file postfix (default: _deduped)')
    parser.add_argument('--detect-trailing-url', action='store_true', 
                       help='Detect and deduplicate URLs with trailing numbers, keeping the base URL')
    parser.add_argument('--out-dir', type=str, help='Output directory (default: same as input file)')
    parser.add_argument('--workers', type=int, default=4, 
                       help='Number of concurrent workers (default: 4)')
    
    args = parser.parse_args()
    
    # Validate input
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input path does not exist: {input_path}", file=sys.stderr)
        sys.exit(1)
    
    # Find all files to process
    files_to_process = find_files(input_path, args)
    
    if not files_to_process:
        print("No files found to process with the given criteria.", file=sys.stderr)
        sys.exit(1)
    
    print(f"Found {len(files_to_process)} file(s) to process")
    print(f"Using {args.workers} concurrent workers\n")
    
    # Initialize statistics
    stats = DeduplicationStats()
    stats.total_files = len(files_to_process)
    
    # Process files concurrently
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(process_file, file_path, args, stats): file_path
            for file_path in files_to_process
        }
        
        for future in as_completed(futures):
            file_path = futures[future]
            try:
                future.result()
            except Exception as e:
                print(f"Unexpected error with {file_path}: {str(e)}", file=sys.stderr)
                stats.add_error()
    
    # Print summary
    stats.print_summary()


if __name__ == '__main__':
    main()