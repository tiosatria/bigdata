import argparse
import sys
import json
import logging
import time
from redis import Redis, RedisError
from scrapy.utils.project import get_project_settings
from scrapy.utils.log import configure_logging
from urllib.parse import urlparse, urlunparse
from pathlib import Path


def setup_logger() -> logging.Logger:
    """Setup logger similar to push.py"""
    configure_logging(install_root_handler=False)
    logger = logging.getLogger("failed_url_pusher")
    logger.setLevel(logging.INFO)

    if logger.hasHandlers():
        logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def connect_redis(redis_url: str, logger: logging.Logger) -> Redis:
    """Connect to Redis instance"""
    try:
        # Work around slow Windows resolution/IPv6 fallback for 'localhost'
        parsed = urlparse(redis_url)
        host = parsed.hostname or ""
        if host.lower() == "localhost":
            new_netloc = parsed.netloc.replace("localhost", "127.0.0.1", 1)
            patched_url = urlunparse((parsed.scheme, new_netloc, parsed.path,
                                      parsed.params, parsed.query, parsed.fragment))
            logger.info(f"Using 127.0.0.1 instead of 'localhost' for Redis: {patched_url}")
        else:
            patched_url = redis_url

        client = Redis.from_url(
            patched_url,
            decode_responses=True,
            socket_connect_timeout=3.0,
            socket_timeout=5.0,
            health_check_interval=0,
        )
        client.ping()
        logger.info(f"Connected to Redis at {patched_url}")
        return client
    except RedisError as e:
        logger.error(f"Redis connection failed: {e}")
        sys.exit(1)


def load_failed_urls(file_path: str, error_codes: list[int] | None, logger: logging.Logger) -> list[dict]:
    """Load failed URLs from JSONL file, optionally filtered by error codes"""
    if not Path(file_path).exists():
        logger.error(f"File not found: {file_path}")
        sys.exit(1)

    failed_urls = []
    total_lines = 0
    skipped = 0

    logger.info(f"Loading failed URLs from: {file_path}")
    if error_codes:
        logger.info(f"Filtering by error codes: {error_codes}")

    t0 = time.perf_counter()

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            for line_num, line in enumerate(f, 1):
                total_lines += 1
                line = line.strip()
                if not line:
                    continue

                try:
                    record = json.loads(line)

                    # Filter by error codes if specified
                    if error_codes:
                        response = record.get('response', {})
                        status = response.get('status')

                        # Also check reason field for HTTP codes
                        reason = record.get('reason', '')
                        reason_code = None
                        if reason.startswith('HTTP '):
                            try:
                                reason_code = int(reason.split()[1])
                            except (IndexError, ValueError):
                                pass

                        # Match either status or reason code against any of the specified codes
                        if status not in error_codes and reason_code not in error_codes:
                            skipped += 1
                            continue

                    # Extract all fields for selective inclusion later
                    url_data = {
                        'url': record.get('url'),
                        'spider': record.get('spider'),
                        'meta': record.get('meta', {}),
                        'method': record.get('method', 'GET'),
                        'headers': record.get('headers', {}),
                        'cookies': record.get('cookies', {}),
                        'priority': record.get('priority', 0),
                    }

                    if not url_data['url']:
                        logger.warning(f"Line {line_num}: Missing URL, skipping")
                        skipped += 1
                        continue

                    failed_urls.append(url_data)

                except json.JSONDecodeError as e:
                    logger.warning(f"Line {line_num}: Invalid JSON - {e}")
                    skipped += 1
                    continue
                except Exception as e:
                    logger.warning(f"Line {line_num}: Error processing record - {e}")
                    skipped += 1
                    continue

    except Exception as e:
        logger.error(f"Error reading file: {e}")
        sys.exit(1)

    elapsed = time.perf_counter() - t0
    logger.info(f"Loaded {len(failed_urls)} URLs from {total_lines} lines in {elapsed:.3f}s (skipped: {skipped})")

    if not failed_urls:
        logger.error("No valid URLs found to push")
        sys.exit(1)

    return failed_urls


def push_urls_to_redis(redis_client: Redis, urls: list[dict], preserve_options: dict, logger: logging.Logger):
    """Push URLs back to Redis queue with selective field preservation"""
    pushed = 0
    failed = 0
    spider_queues = {}

    t0 = time.perf_counter()

    # Log what's being preserved
    preserved = []
    if preserve_options['meta']:
        preserved.append('meta')
    if preserve_options['cookies']:
        preserved.append('cookies')
    if preserve_options['headers']:
        preserved.append('headers')
    if preserve_options['priority']:
        preserved.append('priority')

    if preserved:
        logger.info(f"Preserving fields: {', '.join(preserved)}")
    else:
        logger.info("Pushing URLs only (no additional fields)")

    if preserve_options['bypass_dedup']:
        logger.info("Deduplication bypass enabled: adding dont_filter=True to meta")

    for idx, url_data in enumerate(urls, 1):
        try:
            spider_name = url_data.get('spider')
            if not spider_name:
                logger.warning(f"URL {idx}: No spider name, skipping")
                failed += 1
                continue

            queue_name = f"{spider_name}:start_urls"

            # Track per-spider stats
            if spider_name not in spider_queues:
                spider_queues[spider_name] = 0

            # Build payload based on preserve options
            payload_data = {'url': url_data['url']}

            # Handle meta field with dedup bypass
            if preserve_options['meta'] or preserve_options['bypass_dedup']:
                meta = url_data.get('meta', {}).copy() if preserve_options['meta'] else {}

                # Add dont_filter to bypass deduplication
                if preserve_options['bypass_dedup']:
                    meta['dont_filter'] = True

                if meta:  # Only add if not empty
                    payload_data['meta'] = meta

            if preserve_options['cookies'] and url_data.get('cookies'):
                payload_data['cookies'] = url_data['cookies']

            if preserve_options['headers'] and url_data.get('headers'):
                payload_data['headers'] = url_data['headers']

            if preserve_options['priority'] and url_data.get('priority') is not None:
                payload_data['priority'] = url_data['priority']

            # If only URL, can push as string; otherwise as JSON dict
            if len(payload_data) == 1:
                payload = url_data['url']
            else:
                payload = json.dumps(payload_data)

            redis_client.lpush(queue_name, payload)
            pushed += 1
            spider_queues[spider_name] += 1

        except RedisError as e:
            logger.error(f"Failed to push URL '{url_data.get('url')}': {e}")
            failed += 1
        except Exception as e:
            logger.error(f"Unexpected error pushing URL '{url_data.get('url')}': {e}")
            failed += 1

        # Periodic progress
        if idx % 1000 == 0:
            elapsed = time.perf_counter() - t0
            rate = pushed / elapsed if elapsed > 0 else 0
            logger.info(f"Progress: pushed {pushed}/{len(urls)} in {elapsed:.2f}s ({rate:.1f} ops/s)")

    elapsed = time.perf_counter() - t0
    rate = pushed / elapsed if elapsed > 0 else 0

    logger.info(f"Pushed {pushed} URLs in {elapsed:.3f}s (failed: {failed}) — {rate:.1f} ops/s")

    # Show per-spider breakdown
    if spider_queues:
        logger.info("Per-spider breakdown:")
        for spider, count in sorted(spider_queues.items()):
            logger.info(f"  {spider}: {count} URLs")


def main():
    parser = argparse.ArgumentParser(
        description="Push failed URLs from JSONL file back to Redis spider queue.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Push all URLs with meta only (default) - BYPASSES DEDUP
  python -m resume -i failed_request.jsonl

  # Push only 403 errors with meta - BYPASSES DEDUP
  python -m resume -i failed_request.jsonl --codes 403

  # Push 403 and 404 errors with meta, headers, and priority - BYPASSES DEDUP
  python -m resume -i failed_request.jsonl --codes 403 404 --preserve headers priority

  # Push all URLs with all fields preserved - BYPASSES DEDUP
  python -m resume -i failed_request.jsonl --preserve cookies headers priority

  # Push URLs without bypassing dedup (will be filtered if already seen)
  python -m resume -i failed_request.jsonl --no-bypass-dedup
        """
    )
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Path to failed_request.jsonl file'
    )
    parser.add_argument(
        '--codes',
        type=int,
        nargs='+',
        help='Filter by specific HTTP error codes (e.g., --codes 403 404 500)'
    )
    parser.add_argument(
        '--preserve',
        nargs='+',
        choices=['cookies', 'headers', 'priority', 'meta'],
        default=[],
        help='Additional fields to preserve when pushing URLs. Meta is included by default unless --no-meta is set.'
    )
    parser.add_argument(
        '--no-meta',
        action='store_true',
        help='Do not include meta field (overrides default behavior)'
    )
    parser.add_argument(
        '--no-bypass-dedup',
        action='store_true',
        help='Do not add dont_filter=True to meta. URLs may be filtered by dedup if already seen.'
    )
    args = parser.parse_args()

    logger = setup_logger()
    logger.info("Failed URL Pusher initialized")

    t_main = time.perf_counter()

    # Load project settings
    logger.info('Loading project settings...')
    t0 = time.perf_counter()
    settings = get_project_settings()
    logger.info(f"Project settings loaded in {time.perf_counter() - t0:.3f}s")

    # Connect to Redis
    redis_url = settings.get('REDIS_URL', 'redis://localhost:6379')
    logger.info('Connecting to Redis...')
    t0 = time.perf_counter()
    redis_client = connect_redis(redis_url, logger)
    logger.info(f"Connected to Redis in {time.perf_counter() - t0:.3f}s")

    # Load failed URLs
    logger.info('Loading failed URLs...')
    t0 = time.perf_counter()
    urls = load_failed_urls(args.input, args.codes, logger)
    logger.info(f"Loaded {len(urls)} URLs in {time.perf_counter() - t0:.3f}s")

    # Determine what to preserve
    preserve_options = {
        'meta': not args.no_meta,  # Meta is default unless explicitly disabled
        'cookies': 'cookies' in args.preserve,
        'headers': 'headers' in args.preserve,
        'priority': 'priority' in args.preserve,
        'bypass_dedup': not args.no_bypass_dedup,  # Bypass dedup by default
    }

    # Push to Redis
    logger.info('Pushing URLs to Redis...')
    push_urls_to_redis(redis_client, urls, preserve_options, logger)

    logger.info(f"Total runtime: {time.perf_counter() - t_main:.3f}s")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        logging.getLogger("failed_url_pusher").info("Interrupted by user")
        sys.exit(0)
    except Exception as e:
        logging.getLogger("failed_url_pusher").exception(f"Fatal error: {e}")
        sys.exit(1)