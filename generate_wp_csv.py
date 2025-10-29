#!/usr/bin/env python3
"""
Generate a CSV for the WordPress REST spider from site_cfg.yaml.

Reads the YAML configuration, takes the first start URL for each domain,
normalizes it to scheme+netloc (root), probes for a WordPress REST API,
and writes a CSV containing only sites that appear to be WordPress.

Output CSV columns:
  - url               (normalized site root, e.g., https://example.com)
  - use_proxy         (boolean from YAML, preserved)
  - use_playwright    (boolean from YAML, preserved)
  - bypass_cf         (optional boolean from YAML, preserved if present)

Usage:
  python generate_wp_csv.py \
      --config site_cfg.yaml \
      --output wordpress_sources.csv \
      [--timeout 10]

The resulting CSV can be fed into the bigdata.spiders.wordpress_spider via
  scrapy crawl wordpress -a csv_path=wordpress_sources.csv

Note: Detection is based on the standard WordPress REST posts endpoint and
checking X-WP-Total and X-WP-TotalPages headers, mirroring the spider logic.
"""

import argparse
import csv
import sys
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse, urlunparse

import requests
import yaml


DEFAULT_TIMEOUT = 10
DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
)


def normalize_root(url: str) -> Optional[str]:
    if not url:
        return None
    p = urlparse(url)
    scheme = p.scheme or 'https'
    netloc = p.netloc or p.path
    if not netloc:
        return None
    return urlunparse((scheme, netloc, '', '', '', ''))


def has_wp_headers(resp: requests.Response) -> bool:
    # Case-insensitive header access via dict
    h = resp.headers
    total_pages = h.get('X-WP-TotalPages') or h.get('x-wp-totalpages')
    total = h.get('X-WP-Total') or h.get('x-wp-total')
    if not total_pages or not total:
        return False
    try:
        int(str(total_pages).strip())
        int(str(total).strip())
        return True
    except Exception:
        return False


def is_wordpress_site(base: str, session: requests.Session, timeout: int) -> bool:
    # Try canonical and rest_route variants
    candidates = [
        f"{base}/wp-json/wp/v2/posts?per_page=1",
        f"{base}/?rest_route=/wp/v2/posts&per_page=1",
    ]
    for url in candidates:
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
        except Exception:
            continue
        if resp.status_code >= 400:
            continue
        if has_wp_headers(resp):
            return True
        # Some servers omit headers but still return a JSON list of posts.
        # As a fallback, accept a JSON array response.
        try:
            data = resp.json()
            if isinstance(data, list):
                return True
        except Exception:
            pass
    return False


def load_yaml(path: Path) -> Dict:
    with path.open('r', encoding='utf-8') as f:
        return yaml.safe_load(f) or {}


def main():
    parser = argparse.ArgumentParser(description='Generate CSV of WordPress sites from site_cfg.yaml')
    parser.add_argument('-c', '--config', default='site_cfg.yaml', help='Path to YAML config (default: site_cfg.yaml)')
    parser.add_argument('-o', '--output', default='wordpress_sources.csv', help='Output CSV path (default: wordpress_sources.csv)')
    parser.add_argument('--timeout', type=int, default=DEFAULT_TIMEOUT, help=f'Request timeout in seconds (default: {DEFAULT_TIMEOUT})')

    args = parser.parse_args()

    cfg_path = Path(args.config)
    if not cfg_path.exists():
        print(f"Error: config not found: {cfg_path}")
        sys.exit(1)

    cfg = load_yaml(cfg_path)
    domains = cfg.get('domains') or {}
    if not domains:
        print('No domains found in YAML.')
        sys.exit(1)

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers.update({'User-Agent': DEFAULT_USER_AGENT, 'Accept': 'application/json, */*;q=0.1'})

    rows = []
    total = 0
    wp_count = 0

    print(f"Scanning {len(domains)} domain configs for WordPress...")

    for name, dcfg in domains.items():
        total += 1
        start_urls = (dcfg or {}).get('start_urls') or []
        if not start_urls:
            print(f"- {name}: skipped (no start_urls)")
            continue
        root = normalize_root(start_urls[0])
        if not root:
            print(f"- {name}: skipped (invalid start_url)")
            continue

        # Optional: quick root request to ensure reachability
        try:
            session.get(root, timeout=args.timeout, allow_redirects=True)
        except Exception as e:
            print(f"- {name}: unreachable root ({e})")
            continue

        try:
            is_wp = is_wordpress_site(root, session, args.timeout)
        except Exception as e:
            print(f"- {name}: detection error ({e})")
            continue

        if is_wp:
            wp_count += 1
            row = {
                'url': root,
                'use_proxy': str(bool(dcfg.get('use_proxy', False))).lower(),
                'use_playwright': str(bool(dcfg.get('use_playwright', False))).lower(),
            }
            if 'bypass_cf' in dcfg:
                row['bypass_cf'] = str(bool(dcfg.get('bypass_cf', False))).lower()
            rows.append(row)
            print(f"+ {name}: WordPress ✔  -> {root}")
        else:
            print(f"- {name}: not WordPress ✖")

    fieldnames = ['url', 'use_proxy', 'use_playwright']
    # include bypass_cf if any row has it
    if any('bypass_cf' in r for r in rows):
        fieldnames.append('bypass_cf')

    with out_path.open('w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in rows:
            writer.writerow({k: r.get(k, '') for k in fieldnames})

    print('\n' + '-'*80)
    print(f"Done. {wp_count}/{total} domains appear to be WordPress.")
    print(f"CSV written: {out_path}")


if __name__ == '__main__':
    main()
