#!/usr/bin/env python3
"""
WordPress Post Count Scanner
Efficiently scans multiple sites to extract WordPress post counts via REST API.
"""

import argparse
import asyncio
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Optional
from urllib.parse import urlparse, urljoin
import aiohttp
import aiofiles
from tqdm.asyncio import tqdm


class PostCountScanner:
    def __init__(self, workers: int = 20, timeout: int = 10, output_file: str = "wp_count_result.csv",
                 log_file: Optional[str] = None, batch_size: int = 100):
        self.workers = workers
        self.timeout = aiohttp.ClientTimeout(total=timeout)
        self.output_file = output_file
        self.log_file = log_file
        self.batch_size = batch_size
        self.results_buffer = []
        self.semaphore = asyncio.Semaphore(workers)

    def normalize_url(self, site: str) -> str:
        """Normalize site URL to ensure proper format."""
        site = site.strip()
        if not site:
            return ""

        if not site.startswith(('http://', 'https://')):
            site = 'https://' + site

        return site

    async def log_message(self, message: str):
        """Log messages to file if log_file is specified."""
        if self.log_file:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            async with aiofiles.open(self.log_file, 'a') as f:
                await f.write(f"[{timestamp}] {message}\n")

    async def get_post_count(self, session: aiohttp.ClientSession, site: str) -> Tuple[str, int]:
        """
        Get post count for a single site.
        Returns: (site, post_count)
        - post_count = -1: Not a WordPress site
        - post_count = 0: WordPress site but failed to get count
        - post_count > 0: Successfully retrieved post count
        """
        async with self.semaphore:
            normalized_site = self.normalize_url(site)

            if not normalized_site:
                await self.log_message(f"Invalid site: {site}")
                return (site, -1)

            # Try to access WordPress REST API endpoint
            api_url = urljoin(normalized_site, '/wp-json/wp/v2/posts')

            try:
                async with session.get(api_url, timeout=self.timeout, allow_redirects=True) as response:
                    # Check if this is a WordPress site
                    if response.status == 404:
                        # Not a WordPress site or REST API disabled
                        await self.log_message(f"Not WordPress or API disabled: {site}")
                        return (site, -1)

                    # WordPress site detected
                    if response.status == 200:
                        # Check for post count in headers
                        headers = response.headers

                        # Try different header names
                        post_count = None
                        for header_name in ['X-WP-Total', 'x-wp-total', 'X-Wp-Total']:
                            if header_name in headers:
                                try:
                                    post_count = int(headers[header_name])
                                    await self.log_message(f"Success: {site} -> {post_count} posts")
                                    return (site, post_count)
                                except (ValueError, TypeError):
                                    continue

                        # WordPress site but couldn't get count from headers
                        await self.log_message(f"WordPress but no count header: {site}")
                        return (site, 0)

                    # Other status codes from WordPress
                    if response.status in [401, 403]:
                        # WordPress site but access restricted
                        await self.log_message(f"WordPress but restricted: {site} (HTTP {response.status})")
                        return (site, 0)

                    # Assume not WordPress for other errors
                    await self.log_message(f"Unknown status: {site} (HTTP {response.status})")
                    return (site, -1)

            except asyncio.TimeoutError:
                await self.log_message(f"Timeout: {site}")
                return (site, -1)
            except aiohttp.ClientConnectorError:
                await self.log_message(f"Connection error: {site}")
                return (site, -1)
            except aiohttp.ClientError as e:
                await self.log_message(f"Client error: {site} - {str(e)}")
                return (site, -1)
            except Exception as e:
                await self.log_message(f"Unexpected error: {site} - {str(e)}")
                return (site, -1)

    async def flush_results(self):
        """Flush buffered results to CSV file."""
        if not self.results_buffer:
            return

        # Check if file exists to determine if we need to write header
        file_exists = Path(self.output_file).exists()

        async with aiofiles.open(self.output_file, 'a', newline='') as f:
            # Write all buffered results
            for site, count in self.results_buffer:
                await f.write(f"{site},{count}\n")

        self.results_buffer.clear()

    async def process_sites(self, sites: List[str]):
        """Process multiple sites with progress tracking."""
        connector = aiohttp.TCPConnector(limit=self.workers, limit_per_host=5)

        async with aiohttp.ClientSession(
                connector=connector,
                headers={'User-Agent': 'WordPress-Post-Counter/1.0'}
        ) as session:
            # Create progress bar
            pbar = tqdm(total=len(sites), desc="Scanning sites", unit="site")

            async def process_with_progress(site):
                result = await self.get_post_count(session, site)
                self.results_buffer.append(result)

                # Batch flush
                if len(self.results_buffer) >= self.batch_size:
                    await self.flush_results()

                pbar.update(1)
                return result

            # Process all sites
            await asyncio.gather(*[process_with_progress(site) for site in sites])

            # Final flush
            await self.flush_results()

            pbar.close()

    async def run(self, sites: List[str]):
        """Main execution method."""
        # Clear output file
        Path(self.output_file).write_text('')

        if self.log_file:
            Path(self.log_file).write_text('')

        print(f"Starting scan of {len(sites)} sites with {self.workers} workers...")
        print(f"Output: {self.output_file}")
        if self.log_file:
            print(f"Logs: {self.log_file}")

        await self.process_sites(sites)

        print(f"\n✓ Scan complete! Results saved to {self.output_file}")


def load_sites_from_file(filename: str) -> List[str]:
    """Load sites from a text file."""
    try:
        with open(filename, 'r') as f:
            sites = [line.strip() for line in f if line.strip()]
        return sites
    except FileNotFoundError:
        print(f"Error: File '{filename}' not found.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error reading file '{filename}': {e}", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description='WordPress Post Count Scanner - Efficiently scan multiple sites for post counts',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --site example.com
  %(prog)s --site-list sites.txt
  %(prog)s --sites example.com example2.com example3.com
  %(prog)s --site-list sites.txt -w 50 -o results.csv --logs scan.log
        """
    )

    # Input options
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument('--site', type=str, help='Single site to scan')
    input_group.add_argument('--site-list', type=str, help='File containing list of sites (one per line)')
    input_group.add_argument('--sites', type=str, nargs='+', help='Multiple sites to scan')

    # Configuration options
    parser.add_argument('-w', '--workers', type=int, default=20,
                        help='Number of concurrent workers (default: 20)')
    parser.add_argument('-o', '--output', type=str, default='wp_count_result.csv',
                        help='Output CSV file (default: wp_count_result.csv)')
    parser.add_argument('--logs', type=str, default=None,
                        help='Log file for detailed scan information (optional)')
    parser.add_argument('-t', '--timeout', type=int, default=10,
                        help='Timeout per request in seconds (default: 10)')
    parser.add_argument('-b', '--batch-size', type=int, default=100,
                        help='Number of results to buffer before flushing (default: 100)')

    args = parser.parse_args()

    # Determine sites to scan
    if args.site:
        sites = [args.site]
    elif args.site_list:
        sites = load_sites_from_file(args.site_list)
    else:  # args.sites
        sites = args.sites

    if not sites:
        print("Error: No sites to scan.", file=sys.stderr)
        sys.exit(1)

    print(f"Loaded {len(sites)} site(s) to scan")

    # Create and run scanner
    scanner = PostCountScanner(
        workers=args.workers,
        timeout=args.timeout,
        output_file=args.output,
        log_file=args.logs,
        batch_size=args.batch_size
    )

    # Run async scanner
    try:
        asyncio.run(scanner.run(sites))
    except KeyboardInterrupt:
        print("\n\nScan interrupted by user. Partial results saved.")
        sys.exit(130)
    except Exception as e:
        print(f"\nFatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()