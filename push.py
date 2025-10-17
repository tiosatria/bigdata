import argparse
import sys
import json
import logging
import time
from dataclasses import asdict
from typing import Any
from redis import Redis, RedisError
from scrapy.spiderloader import SpiderLoader
from scrapy.utils.project import get_project_settings
from bigdata.domain_configs import DomainConfigRegistry
from bigdata.domain_configs.domain_config import Seed
from scrapy.utils.log import configure_logging
from urllib.parse import urlparse, urlunparse

def setup_logger() -> logging.Logger:
    # Disable Scrapy's default log interception
    configure_logging(install_root_handler=False)
    logger = logging.getLogger("seed_pusher")
    logger.setLevel(logging.INFO)

    # Clear existing handlers (important when Scrapy imports reinit logging)
    if logger.hasHandlers():
        logger.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter("[%(asctime)s] [%(levelname)s] %(message)s", "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.propagate = False
    return logger


def connect_redis(redis_url: str, logger: logging.Logger) -> Redis:
    try:
        # Work around slow Windows resolution/IPv6 fallback for 'localhost'
        parsed = urlparse(redis_url)
        host = parsed.hostname or ""
        if host.lower() == "localhost":
            new_netloc = parsed.netloc.replace("localhost", "127.0.0.1", 1)
            patched_url = urlunparse((parsed.scheme, new_netloc, parsed.path, parsed.params, parsed.query, parsed.fragment))
            logger.info(f"Using 127.0.0.1 instead of 'localhost' for Redis to avoid DNS/IPv6 delays: {patched_url}")
        else:
            patched_url = redis_url

        client = Redis.from_url(
            patched_url,
            decode_responses=True,
            socket_connect_timeout=3.0,  # speed up failed/slow connects
            socket_timeout=5.0,
            health_check_interval=0,
        )
        client.ping()
        logger.info(f"Connected to Redis at {patched_url}")
        return client
    except RedisError as e:
        logger.error(f"Redis connection failed: {e}")
        sys.exit(1)


def validate_spider(spider_loader: SpiderLoader, spider_name: str):
    available = spider_loader.list()
    if spider_name not in available:
        raise ValueError(f"Spider '{spider_name}' not found. Available: {', '.join(available)}")


def collect_seeds(domains: list[str], logger: logging.Logger) -> list[Any]:
    all_seeds = []

    logger.info('Loading domain registry...')
    t0 = time.perf_counter()
    DomainConfigRegistry.load_all_configs()
    load_time = time.perf_counter() - t0

    doms = DomainConfigRegistry.get_all_domains()
    logger.info(f"Domain registry loaded in {load_time:.3f}s. Total registered domains: {len(doms)}")

    for domain in domains:
        d_start = time.perf_counter()
        try:
            domain_config = DomainConfigRegistry.get(domain)
        except Exception as e:
            logger.error(f"Error retrieving config for domain '{domain}': {e}")
            continue

        if not domain_config:
            logger.error(f"No config found for domain '{domain}'")
            logger.error(f"Available domains: {', '.join(doms)}")
            continue

        seeds = getattr(domain_config, "seeds", None)
        if not seeds:
            logger.warning(f"No seeds available for domain '{domain}'")
            continue

        if isinstance(seeds, str):
            seeds = [seeds]
        elif not isinstance(seeds, list):
            logger.warning(f"Invalid seed type for domain '{domain}': {type(seeds).__name__}")
            continue

        all_seeds.extend(seeds)
        d_elapsed = time.perf_counter() - d_start
        logger.info(f"Collected {len(seeds)} seeds from domain '{domain}' in {d_elapsed:.3f}s")

    if not all_seeds:
        logger.error("No valid seeds collected from provided domains.")
        sys.exit(1)

    return all_seeds


def push_seeds(redis_client: Redis, spider_name: str, seeds: list[str|dict|Seed], logger: logging.Logger):
    queue_name = f"{spider_name}:start_urls"
    pushed = 0
    failed = 0
    t0 = time.perf_counter()

    for idx, seed in enumerate(seeds, 1):
        try:
            seed=seed.to_dict()
            payload = json.dumps(seed) if isinstance(seed, (dict, list, Seed)) else str(seed)
            redis_client.lpush(queue_name, payload)
            pushed += 1
        except RedisError as e:
            logger.error(f"Failed to push seed '{seed}': {e}")
            failed += 1
        # Periodic progress
        if idx % 1000 == 0:
            elapsed = time.perf_counter() - t0
            rate = pushed / elapsed if elapsed > 0 else 0
            logger.info(f"Progress: pushed {pushed}/{len(seeds)} in {elapsed:.2f}s ({rate:.1f} ops/s)")

    elapsed = time.perf_counter() - t0
    rate = pushed / elapsed if elapsed > 0 else 0
    logger.info(f"Pushed {pushed} seeds to '{queue_name}' in {elapsed:.3f}s (failed: {failed}) — {rate:.1f} ops/s")


def main():
    parser = argparse.ArgumentParser(description="Push seeds of specific domains to a Redis spider queue.")
    parser.add_argument('--domains', required=True, nargs='+', help='List of domain identifiers to push seeds from.')
    parser.add_argument('--spider', required=True, help='Target spider name to push the seeds into.')
    args = parser.parse_args()

    logger = setup_logger()
    logger.info("Logger initialized.")

    t_main = time.perf_counter()

    logger.info('Getting project settings...')
    t0 = time.perf_counter()
    settings = get_project_settings()
    logger.info(f"Project settings loaded in {time.perf_counter()-t0:.3f}s")

    redis_url = settings.get('REDIS_URL', 'redis://localhost:6379')
    logger.info('Connecting to redis instance...')
    t0 = time.perf_counter()
    redis_client = connect_redis(redis_url, logger)
    logger.info(f"Connected to Redis in {time.perf_counter()-t0:.3f}s")

    logger.info('Getting spider info...')
    t0 = time.perf_counter()
    spider_loader = SpiderLoader.from_settings(settings)
    validate_spider(spider_loader, args.spider)
    logger.info(f"Spider '{args.spider}' validated in {time.perf_counter()-t0:.3f}s")

    logger.info('Collecting seeds from domain registry...')
    t0 = time.perf_counter()
    seeds = collect_seeds(args.domains, logger)
    logger.info(f"Collected total {len(seeds)} seeds in {time.perf_counter()-t0:.3f}s")

    push_seeds(redis_client, args.spider, seeds, logger)

    logger.info(f"Total push.py runtime: {time.perf_counter()-t_main:.3f}s")


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        logging.getLogger("seed_pusher").exception(f"Fatal error: {e}")
        sys.exit(1)
