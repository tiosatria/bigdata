#!/usr/bin/env python3
"""
Main orchestrator for JSONL data cleaning pipeline
"""
import argparse
import os
import sys
from pathlib import Path
from multiprocessing import Pool, Manager
from tqdm import tqdm
import json

from config_loader import ConfigLoader
from processors.deduplicator import Deduplicator
from processors.filter import Filter
from processors.validator import Validator
from key_mapper import KeyMapper
from cleaners import CleanerFactory
from utils.logger import setup_logger, get_logger
from utils.helpers import extract_site_key, ensure_dir


class Pipeline:
    def __init__(self, config_path='site_cfg.yaml'):
        self.config_loader = ConfigLoader(config_path)
        self.global_config = self.config_loader.get_global_config()
        setup_logger(self.global_config['paths']['logs'])
        self.logger = get_logger('orchestrator')
        self.stats = Manager().dict()

    def process_file(self, input_path):
        """Process a single JSONL file"""
        filename = Path(input_path).stem
        site_key = extract_site_key(filename)

        # Get site-specific config
        site_config = self.config_loader.get_site_config(site_key)
        logger = get_logger(f'worker.{site_key}')

        logger.info(f"Processing {filename} with config: {site_key}")

        # Initialize components
        deduplicator = Deduplicator()
        filter_proc = Filter(site_config)
        validator = Validator(site_config)
        key_mapper = KeyMapper(site_config)

        # Initialize cleaners
        cleaners = []
        for step in site_config['cleaning_pipeline']:
            if step['enabled']:
                cleaner = CleanerFactory.create(step['name'], step.get('params', {}), site_config)
                cleaners.append(cleaner)

        # Prepare output path
        output_dir = Path(site_config['paths']['output'])
        ensure_dir(output_dir)
        output_path = output_dir / f"{filename}_cleaned.jsonl"

        # Stats tracking
        stats = {
            'total': 0,
            'dedupe_filtered': 0,
            'exclude_filtered': 0,
            'include_filtered': 0,
            'validation_failed': 0,
            'processed': 0,
            'errors': 0
        }

        # Process records
        try:
            with open(input_path, 'r', encoding='utf-8') as infile, \
                    open(output_path, 'w', encoding='utf-8') as outfile:

                # Count total lines for progress
                total_lines = sum(1 for _ in open(input_path, 'r', encoding='utf-8'))

                infile.seek(0)
                pbar = tqdm(
                    total=total_lines,
                    desc=f"{filename[:30]}",
                    position=None,
                    leave=False,
                    unit='rec'
                )

                for line_num, line in enumerate(infile, 1):
                    stats['total'] += 1
                    pbar.update(1)

                    try:
                        record = json.loads(line.strip())

                        # Step 1: Deduplication
                        url = self._get_nested(record, 'metadata.url') or ''
                        if deduplicator.is_duplicate(url):
                            stats['dedupe_filtered'] += 1
                            logger.debug(f"Duplicate URL: {url}")
                            continue
                        deduplicator.add(url)

                        # Step 2: Filtering
                        filter_result = filter_proc.apply(record)
                        if filter_result == 'excluded':
                            stats['exclude_filtered'] += 1
                            continue
                        elif filter_result == 'not_included':
                            stats['include_filtered'] += 1
                            continue

                        # Step 3: Cleaning pipeline
                        for cleaner in cleaners:
                            record = cleaner.clean(record)
                            if record is None:
                                logger.debug(f"Record filtered by {cleaner.name}")
                                break

                        if record is None:
                            stats['exclude_filtered'] += 1
                            continue

                        # Step 4: Key mapping
                        output_record = key_mapper.map(record)

                        # Step 5: Validation
                        if not validator.validate(output_record):
                            stats['validation_failed'] += 1
                            logger.debug(f"Validation failed for URL: {url}")
                            continue

                        # Write output
                        outfile.write(json.dumps(output_record, ensure_ascii=False) + '\n')
                        stats['processed'] += 1

                    except json.JSONDecodeError as e:
                        stats['errors'] += 1
                        logger.error(f"JSON decode error at line {line_num}: {e}")
                    except Exception as e:
                        stats['errors'] += 1
                        logger.error(f"Error processing line {line_num}: {e}", exc_info=True)

                pbar.close()

        except Exception as e:
            logger.error(f"Error processing file {filename}: {e}", exc_info=True)
            stats['errors'] += 1

        # Log stats
        logger.info(f"Completed {filename}: {stats}")
        return filename, stats

    def _get_nested(self, obj, path):
        """Get nested value from object using dot notation"""
        keys = path.split('.')
        val = obj
        for key in keys:
            if isinstance(val, dict):
                val = val.get(key)
            else:
                return None
            if val is None:
                return None
        return val

    def run(self):
        """Main execution"""
        input_dir = Path(self.global_config['paths']['input'])

        if not input_dir.exists():
            self.logger.error(f"Input directory not found: {input_dir}")
            sys.exit(1)

        # Find all JSONL files
        jsonl_files = list(input_dir.glob('*.jsonl'))

        if not jsonl_files:
            self.logger.warning(f"No JSONL files found in {input_dir}")
            sys.exit(0)

        self.logger.info(f"Found {len(jsonl_files)} files to process")

        # Process files
        workers = self.global_config.get('workers', 12)
        limit = self.global_config.get('limit', 0)

        if limit > 0:
            jsonl_files = jsonl_files[:limit]
            self.logger.info(f"Limiting to {limit} files")

        # File-level progress bar
        file_pbar = tqdm(
            total=len(jsonl_files),
            desc="Files",
            position=0,
            unit='file'
        )

        # Process in parallel
        with Pool(processes=workers) as pool:
            results = []
            for result in pool.imap_unordered(self.process_file, jsonl_files):
                results.append(result)
                file_pbar.update(1)

        file_pbar.close()

        # Aggregate stats
        total_stats = {
            'total': 0,
            'dedupe_filtered': 0,
            'exclude_filtered': 0,
            'include_filtered': 0,
            'validation_failed': 0,
            'processed': 0,
            'errors': 0
        }

        for filename, stats in results:
            for key in total_stats:
                total_stats[key] += stats[key]

        self.logger.info("=" * 80)
        self.logger.info("FINAL STATISTICS")
        self.logger.info("=" * 80)
        self.logger.info(f"Total records: {total_stats['total']}")
        self.logger.info(f"Deduplicated: {total_stats['dedupe_filtered']}")
        self.logger.info(f"Excluded by filters: {total_stats['exclude_filtered']}")
        self.logger.info(f"Not included by filters: {total_stats['include_filtered']}")
        self.logger.info(f"Validation failed: {total_stats['validation_failed']}")
        self.logger.info(f"Successfully processed: {total_stats['processed']}")
        self.logger.info(f"Errors: {total_stats['errors']}")
        self.logger.info("=" * 80)


def main():
    parser = argparse.ArgumentParser(description='JSONL Data Cleaning Pipeline')
    parser.add_argument(
        '-c', '--config',
        default='site_cfg.yaml',
        help='Path to configuration YAML file (default: site_cfg.yaml)'
    )

    args = parser.parse_args()

    pipeline = Pipeline(args.config)
    pipeline.run()


if __name__ == '__main__':
    main()