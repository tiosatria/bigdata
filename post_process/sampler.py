#!/usr/bin/env python3
"""
JSON/JSONL Parallel Sampler
Efficiently samples random records from JSON/JSONL files with parallel processing.
"""

import json
import argparse
import random
from pathlib import Path
from typing import List, Dict, Any
from concurrent.futures import ProcessPoolExecutor, as_completed
from tqdm import tqdm
import sys

from post_process.jsonloader import JSONLoader


def count_lines(file_path: Path) -> int:
    """Count total records using JSONLoader (lines for JSONL, length for JSON)."""
    loader = JSONLoader(file_path)
    return loader.count()


def load_json_array(file_path: Path) -> List[Dict[Any, Any]]:
    """Load JSON array format."""
    with open(file_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_jsonl_chunk(args_tuple):
    """Load a chunk of JSONL file (for parallel processing)."""
    file_path, line_indices = args_tuple
    records = []

    with open(file_path, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            if idx in line_indices:
                try:
                    records.append(json.loads(line.strip()))
                except json.JSONDecodeError:
                    print(f"Warning: Skipping invalid JSON at line {idx + 1}", file=sys.stderr)

    return records


def sample_jsonl_parallel(file_path: Path, n_samples: int, total_lines: int, workers: int) -> List[Dict[Any, Any]]:
    """Sample from JSONL using parallel processing."""
    # Generate random line indices to sample
    sample_indices = set(random.sample(range(total_lines), min(n_samples, total_lines)))

    # Split indices into chunks for parallel processing
    chunk_size = max(1, len(sample_indices) // workers)
    index_chunks = []
    indices_list = sorted(sample_indices)

    for i in range(0, len(indices_list), chunk_size):
        chunk = set(indices_list[i:i + chunk_size])
        index_chunks.append((file_path, chunk))

    # Process chunks in parallel
    all_records = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(load_jsonl_chunk, chunk) for chunk in index_chunks]

        with tqdm(total=len(futures), desc="Loading chunks", unit="chunk") as pbar:
            for future in as_completed(futures):
                records = future.result()
                all_records.extend(records)
                pbar.update(1)

    return all_records


def write_jsonl(records: List[Dict[Any, Any]], output_path: Path):
    """Write records to JSONL format."""
    with open(output_path, 'w', encoding='utf-8') as f:
        for record in tqdm(records, desc="Writing output", unit="record"):
            f.write(json.dumps(record, ensure_ascii=False) + '\n')


def main():
    parser = argparse.ArgumentParser(
        description='Sample random records from JSON/JSONL files with parallel processing',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python sampler.py file.jsonl -n 2000
  python sampler.py file.json --worker 12 -n 5000 -o output.jsonl
  python sampler.py data.jsonl -n 1000 --worker 8 -o samples/
        """
    )

    parser.add_argument('input', type=str, help='Input JSON or JSONL file')
    parser.add_argument('-n', '--samples', type=int, required=True,
                        help='Number of random samples to extract')
    parser.add_argument('--worker', type=int, default=4,
                        help='Number of parallel workers (default: 4)')
    parser.add_argument('-o', '--output', type=str, default='./',
                        help='Output file or directory (default: ./)')
    parser.add_argument('--seed', type=int, default=None,
                        help='Random seed for reproducibility')

    args = parser.parse_args()

    # Set random seed if provided
    if args.seed is not None:
        random.seed(args.seed)

    # Validate input file
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file '{args.input}' not found", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    output_path = Path(args.output)
    if output_path.is_dir() or args.output.endswith('/'):
        output_path = output_path / f"{input_path.stem}_sample_{args.samples}.jsonl"
        output_path.parent.mkdir(parents=True, exist_ok=True)
    else:
        output_path.parent.mkdir(parents=True, exist_ok=True)

    # Detect file format
    is_jsonl = input_path.suffix.lower() == '.jsonl'

    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Samples: {args.samples}")
    print(f"Workers: {args.worker}")
    print(f"Format: {'JSONL' if is_jsonl else 'JSON'}")
    print("-" * 50)

    try:
        if is_jsonl:
            # Process JSONL with parallel sampling
            print("Counting lines...")
            total_lines = count_lines(input_path)
            print(f"Total records: {total_lines:,}")

            if args.samples > total_lines:
                print(f"Warning: Requested samples ({args.samples}) exceeds total records ({total_lines})")
                print(f"Sampling all {total_lines} records instead")

            print(f"Sampling {min(args.samples, total_lines):,} random records...")
            sampled_records = sample_jsonl_parallel(input_path, args.samples, total_lines, args.worker)

        else:
            # Process JSON array
            print("Loading JSON array...")
            all_records = load_json_array(input_path)
            print(f"Total records: {len(all_records):,}")

            if args.samples > len(all_records):
                print(f"Warning: Requested samples ({args.samples}) exceeds total records ({len(all_records)})")
                print(f"Sampling all {len(all_records)} records instead")

            print(f"Sampling {min(args.samples, len(all_records)):,} random records...")
            sampled_records = random.sample(all_records, min(args.samples, len(all_records)))

        # Write output
        print(f"\nWriting {len(sampled_records):,} records to {output_path}...")
        write_jsonl(sampled_records, output_path)

        print(f"\n✓ Successfully created sample file: {output_path}")
        print(f"  Total sampled records: {len(sampled_records):,}")

    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON format - {e}", file=sys.stderr)
        sys.exit(1)
    except MemoryError:
        print("Error: Out of memory. Try using a JSONL format or reduce sample size.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()