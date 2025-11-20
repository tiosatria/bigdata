#!/usr/bin/env python3

import argparse
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import itertools
from tqdm import tqdm
import os


def write_chunk(lines_chunk, output_dir, filename_prefix, file_index):
    """
    Worker function to write a list of lines to a new file.

    Uses 6-digit padding for the file index for better sorting.
    """
    # Format: prefix_000001.jsonl, prefix_000002.jsonl etc.
    output_filename = f"{filename_prefix}_{file_index:06d}.jsonl"
    output_path = output_dir / output_filename

    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            # .writelines() is an efficient way to write a list of strings
            f.writelines(lines_chunk)
        return len(lines_chunk)  # Return number of lines written
    except IOError as e:
        print(f"Error writing to {output_path}: {e}", file=sys.stderr)
        return 0


def main():
    parser = argparse.ArgumentParser(
        description="Split a large JSONL file into smaller chunks concurrently.",
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "input_file",
        type=Path,
        help="The large JSONL file to split."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory to save split files. (default: same as input file)"
    )
    parser.add_argument(
        "--lines",
        type=int,
        default=10000,
        help="Number of lines per split file. (default: 10000)"
    )
    parser.add_argument(
        "-w", "--workers",
        type=int,
        default=None,
        help="Number of worker threads for writing. (default: system's CPU count)"
    )
    parser.add_argument(
        "--prefix",
        type=str,
        default=None,
        help="Prefix for output files. (default: split_{filename})"
    )
    parser.add_argument(
        "--start-from",
        type=int,
        default=1,
        help="Starting index for file names. (default: 1)"
    )

    args = parser.parse_args()

    # --- 1. Validate inputs ---
    if not args.input_file.exists() or not args.input_file.is_file():
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        sys.exit(1)

    if args.lines <= 0:
        print("Error: --lines must be a positive number.", file=sys.stderr)
        sys.exit(1)

    # --- 2. Set defaults based on inputs ---
    output_dir = args.output_dir if args.output_dir is not None else args.input_file.parent

    # Ensure output dir exists
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"Error: Could not create output directory {output_dir}: {e}", file=sys.stderr)
        sys.exit(1)

    prefix = args.prefix if args.prefix is not None else f"split_{args.input_file.stem}"

    # Set worker count. Default to os.cpu_count() or 4 if it can't be determined.
    worker_count = args.workers if args.workers is not None else os.cpu_count() or 4

    # --- 3. Start processing ---
    print(f"Splitting '{args.input_file.name}' into chunks of {args.lines} lines.")
    print(f"Output directory: {output_dir}")
    print(f"File prefix: '{prefix}'")
    print(f"Using {worker_count} worker threads.")
    print("---")

    file_index = args.start_from
    total_lines_written = 0
    futures = []

    try:
        # Use ThreadPoolExecutor for I/O-bound tasks (writing files)
        with ThreadPoolExecutor(max_workers=worker_count) as executor:
            with open(args.input_file, 'r', encoding='utf-8') as f:

                # We don't know the total, so we don't provide it to tqdm.
                # It will show progress as lines/s (records/s).
                with tqdm(unit="lines", desc="Reading input") as pbar:
                    while True:
                        # Read a chunk of lines from the file iterator
                        chunk = list(itertools.islice(f, args.lines))

                        if not chunk:
                            break  # End of file

                        # Submit the write task to the thread pool
                        futures.append(
                            executor.submit(
                                write_chunk,
                                chunk,
                                output_dir,
                                prefix,
                                file_index
                            )
                        )

                        # Update the progress bar by the number of lines we just read
                        pbar.update(len(chunk))
                        file_index += 1

            # --- 4. Wait for all write tasks to complete ---
            print("\nInput file read. Waiting for all file writes to finish...")

            # Use a new tqdm bar to show the progress of *writing*
            for future in tqdm(as_completed(futures), total=len(futures), desc="Writing files"):
                try:
                    lines_written = future.result()
                    total_lines_written += lines_written
                except Exception as e:
                    print(f"A write task failed: {e}", file=sys.stderr)

    except KeyboardInterrupt:
        print("\nProcess interrupted by user. Shutting down...")
        # The 'with' statement for the executor will handle shutdown
        sys.exit(1)
    except Exception as e:
        print(f"\nAn unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

    print("---")
    print("✅ Split complete.")
    print(f"Total lines processed: {total_lines_written}")
    print(f"Total files created: {file_index - args.start_from}")


if __name__ == "__main__":
    main()