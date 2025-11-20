#!/usr/bin/env python3

"""
High-performance, parallel JSONL merger with optional deduplication.

Optimized for large files (50GB+) with maximum throughput on high-end hardware.
Uses producer-consumer pattern with dedicated reader/writer processes to eliminate I/O bottlenecks.
"""

import argparse
import os
import sys
import json
import logging
import signal
from pathlib import Path
from multiprocessing import Process, Manager, Queue, cpu_count
from queue import Empty
from typing import List, Dict, Any, Optional
import time

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(processName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger()

# --- Global flag for graceful shutdown ---
shutdown_flag = False


def signal_handler(signum, frame):
    """Handle Ctrl+C gracefully"""
    global shutdown_flag
    log.warning("\n🛑 Interrupt received! Shutting down gracefully...")
    shutdown_flag = True


signal.signal(signal.SIGINT, signal_handler)


def get_nested_value(obj: Dict[str, Any], key_path: str) -> Optional[str]:
    """
    Get nested dictionary value using dot notation.
    e.g., 'meta.data_info.url' -> obj['meta']['data_info']['url']
    """
    keys = key_path.split('.')
    value = obj
    try:
        for key in keys:
            value = value[key]
        return str(value) if value is not None else None
    except (KeyError, TypeError):
        return None


def reader_process(filepaths: List[str], input_queue: Queue):
    """
    Reads lines from multiple files sequentially and puts them into the input queue.
    This process is I/O bound, so it runs independently to avoid blocking workers.
    """
    global shutdown_flag
    log.info(f"[Reader] Starting to read {len(filepaths)} file(s)")
    lines_read = 0

    try:
        for filepath in filepaths:
            if shutdown_flag:
                break

            log.info(f"[Reader] Reading: {os.path.basename(filepath)}")
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    if shutdown_flag:
                        break

                    # Put tuple of (line, filepath) for better error tracking
                    input_queue.put((line.strip(), filepath))
                    lines_read += 1

    except Exception as e:
        log.error(f"[Reader] Critical error during file read: {e}", exc_info=True)

    finally:
        # Signal workers that no more data is coming
        num_workers = cpu_count()
        for _ in range(num_workers):
            input_queue.put(None)
        log.info(f"[Reader] Finished reading {lines_read:,} lines. Shutting down.")


def worker_process(
        worker_id: int,
        input_queue: Queue,
        output_queue: Queue,
        unique_key: Optional[str],
        seen_keys_proxy: Optional[Dict]
):
    """
    Pulls lines from input queue, validates JSON, checks for duplicates,
    and puts valid results into output queue.
    """
    global shutdown_flag
    processed = 0
    duplicates = 0
    errors = 0

    while not shutdown_flag:
        try:
            item = input_queue.get(timeout=0.1)
        except Empty:
            continue

        if item is None:
            # Sentinel received, stop processing
            break

        line, source_file = item

        if not line:
            continue

        try:
            # Parse JSON
            record = json.loads(line)

            # Check for duplicates if unique_key is specified
            if unique_key and seen_keys_proxy is not None:
                key_value = get_nested_value(record, unique_key)

                if key_value is None:
                    # Key not found in record, skip
                    errors += 1
                    output_queue.put(('ERROR', None))
                    continue

                if key_value in seen_keys_proxy:
                    # Duplicate found
                    duplicates += 1
                    output_queue.put(('DUPLICATE', None))
                    continue

                # Mark as seen
                seen_keys_proxy[key_value] = 1

            # Valid record, pass it through
            output_queue.put(('OK', line))
            processed += 1

        except json.JSONDecodeError as e:
            errors += 1
            output_queue.put(('ERROR', None))
            log.debug(f"[Worker-{worker_id}] JSON decode error: {e}")
        except Exception as e:
            errors += 1
            output_queue.put(('ERROR', None))
            log.debug(f"[Worker-{worker_id}] Unexpected error: {e}")

    # Send sentinel to writer
    output_queue.put(None)
    log.debug(f"[Worker-{worker_id}] Processed: {processed:,}, Duplicates: {duplicates:,}, Errors: {errors:,}")

GENERIC_CATEGORY = [
    "featured",
    "home",
    "blog"
]

def writer_process(output_queue: Queue, output_file: str, num_workers: int):
    """
    Pulls processed results from the output queue and writes them to the output file.
    Returns statistics about the merge operation.
    """
    global shutdown_flag
    log.info(f"[Writer] Starting to write to {os.path.basename(output_file)}")

    sentinels_received = 0
    records_written = 0
    records_duplicate = 0
    records_error = 0

    start_time = time.time()
    last_log_time = start_time
    log_interval = 5.0  # Log every 5 seconds

    try:
        with open(output_file, 'w', encoding='utf-8') as f_out:
            while sentinels_received < num_workers and not shutdown_flag:
                try:
                    result = output_queue.get(timeout=0.5)
                except Empty:
                    # Log periodic progress
                    current_time = time.time()
                    if current_time - last_log_time >= log_interval:
                        elapsed = current_time - start_time
                        rate = records_written / elapsed if elapsed > 0 else 0
                        log.info(f"[Writer] Progress: {records_written:,} written | {rate:,.0f} lines/sec")
                        last_log_time = current_time
                    continue

                if result is None:
                    sentinels_received += 1
                    continue

                status, line = result

                if status == 'OK':
                    f_out.write(line + '\n')
                    records_written += 1
                elif status == 'DUPLICATE':
                    records_duplicate += 1
                elif status == 'ERROR':
                    records_error += 1

    except Exception as e:
        log.error(f"[Writer] Critical error during file write: {e}", exc_info=True)

    finally:
        end_time = time.time()
        elapsed = end_time - start_time
        rate = records_written / elapsed if elapsed > 0 else 0

        log.info(f"[Writer] Finished!")
        log.info(f"  ✓ Written: {records_written:,} records")
        log.info(f"  ⊗ Duplicates: {records_duplicate:,} records")
        log.info(f"  ✗ Errors: {records_error:,} records")
        log.info(f"  ⏱ Time: {elapsed:.2f}s | Rate: {rate:,.2f} lines/sec")

        return records_written, records_duplicate, records_error


def main():
    parser = argparse.ArgumentParser(
        description="High-performance parallel JSONL merger with optional deduplication"
    )

    # --- Input ---
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--from-dir',
        type=str,
        help="Directory containing .jsonl files to merge"
    )
    input_group.add_argument(
        '--from-files',
        nargs='+',
        help="List of .jsonl files to merge"
    )

    # --- Processing ---
    parser.add_argument(
        '--worker',
        type=int,
        default=cpu_count(),
        help=f"Number of worker processes (Default: {cpu_count()})"
    )

    # --- Output ---
    parser.add_argument(
        '--output',
        type=str,
        help="Output file path (Default: first_file_merged.jsonl)"
    )

    # --- Deduplication ---
    parser.add_argument(
        '--unique-key',
        type=str,
        help="JSON key path for deduplication (e.g., 'meta.data_info.url')"
    )

    args = parser.parse_args()

    # --- Collect Input Files ---
    input_files: List[str] = []

    if args.from_dir:
        dir_path = Path(args.from_dir)
        if not dir_path.is_dir():
            log.error(f"Directory not found: {args.from_dir}")
            sys.exit(1)

        input_files = [str(f) for f in dir_path.glob('*.jsonl')]
        if not input_files:
            log.error(f"No .jsonl files found in: {args.from_dir}")
            sys.exit(1)

    elif args.from_files:
        for filepath in args.from_files:
            path = Path(filepath)
            if not path.exists():
                log.error(f"File not found: {filepath}")
                sys.exit(1)
            input_files.append(str(path))

    input_files.sort()  # Deterministic order
    log.info(f"Found {len(input_files)} file(s) to merge")

    # --- Determine Output File ---
    if args.output:
        output_file = args.output
    else:
        first_file = Path(input_files[0])
        output_file = str(first_file.parent / f"{first_file.stem}_merged.jsonl")

    log.info(f"Output will be written to: {output_file}")

    # --- Setup Shared State for Deduplication ---
    manager = Manager()
    seen_keys_proxy = manager.dict() if args.unique_key else None

    if args.unique_key:
        log.info(f"Deduplication enabled on key: '{args.unique_key}'")
    else:
        log.info("Deduplication disabled - records may have duplicates")

    # --- Setup Queues ---
    # Large maxsize to prevent reader from blocking
    input_queue = Queue(maxsize=10000)
    output_queue = Queue(maxsize=10000)

    # --- Setup Processes ---
    num_workers = args.worker

    reader = Process(
        target=reader_process,
        args=(input_files, input_queue)
    )

    workers = []
    for i in range(num_workers):
        p = Process(
            target=worker_process,
            args=(i, input_queue, output_queue, args.unique_key, seen_keys_proxy)
        )
        workers.append(p)

    writer = Process(
        target=writer_process,
        args=(output_queue, output_file, num_workers)
    )

    # --- Start Pipeline ---
    log.info(f"Starting merge with {num_workers} worker processes")
    log.info("Press Ctrl+C to cancel")

    reader.start()
    for p in workers:
        p.start()
    writer.start()

    # --- Wait for Completion ---
    try:
        reader.join()
        for p in workers:
            p.join()
        writer.join()
    except KeyboardInterrupt:
        log.warning("Interrupted by user - cleaning up...")
        reader.terminate()
        for p in workers:
            p.terminate()
        writer.terminate()
        sys.exit(1)

    log.info("--- 🚀 Merge Complete! ---")


if __name__ == "__main__":
    main()