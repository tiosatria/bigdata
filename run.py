#!/usr/bin/env python3
"""
Command-line script to run the universal spider with domain configuration.

Usage:
    python run.py veganchef.com
    python run.py botanical.com --output output.jsonl
    python run.py example-cf-protected.com --config custom_config.yaml

    # List available domains
    python run.py --list
"""

import argparse
import sys
import yaml
from pathlib import Path
from scrapy.crawler import CrawlerProcess
from scrapy.utils.project import get_project_settings
from bigdata.spiders.universal import UniversalSpider


def list_domains(config_file='site_cfg.yaml'):
    """List all configured domains"""
    config_path = Path(config_file)

    if not config_path.exists():
        print(f"Error: Config file '{config_file}' not found.")
        return

    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    if 'domains' not in config:
        print("No domains configured.")
        return

    print("\nConfigured domains:")
    print("-" * 80)

    for domain, settings in config['domains'].items():
        print(f"\n{domain}")
        print(f"  Start URLs: {', '.join(settings.get('start_urls', []))}")
        print(f"  Proxy: {settings.get('use_proxy', False)}")
        print(f"  CF Bypass: {settings.get('bypass_cf', False)}")
        print(f"  Playwright: {settings.get('use_playwright', False)}")

        if settings.get('allow'):
            print(f"  Allow patterns: {len(settings['allow'])} pattern(s)")
        if settings.get('deny'):
            print(f"  Deny patterns: {len(settings['deny'])} pattern(s)")

        # Show custom settings
        if settings.get('settings'):
            print(f"  Custom settings:")
            for key, value in settings['settings'].items():
                print(f"    {key}: {value}")

    print("\n" + "-" * 80)

def main():
    parser = argparse.ArgumentParser(
        description='Run the universal spider with YAML configuration (single domain per run)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s veganchef.com
  %(prog)s botanical.com --output results.jsonl
  %(prog)s example-cf-protected.com --config custom_config.yaml
  %(prog)s --list  # List all configured domains

Note: Only one domain can be crawled per run.
        """
    )

    parser.add_argument(
        'domain',
        nargs='?',
        help='Domain to crawl (must be configured in YAML file). Only ONE domain per run.'
    )

    parser.add_argument(
        '-c', '--config',
        default='site_cfg.yaml',
        help='Path to YAML configuration file (default: site_cfg.yaml)'
    )

    parser.add_argument(
        '-o', '--output',
        help='Output file (e.g., output.jsonl)'
    )

    parser.add_argument(
        '-l', '--list',
        action='store_true',
        help='List all configured domains and exit'
    )

    parser.add_argument(
        '-s', '--set',
        action='append',
        default=[],
        help='Override settings (e.g., -s CONCURRENT_REQUESTS=8)'
    )

    args = parser.parse_args()

    # Handle --list option
    if args.list:
        list_domains(args.config)
        return

    # Validate domain argument
    if not args.domain:
        parser.print_help()
        print("\nError: Please specify a domain to crawl, or use --list to see available domains.")
        sys.exit(1)

    # Verify config file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"Error: Config file '{args.config}' not found.")
        sys.exit(1)

    # Load config to verify domain exists
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)

    domain = args.domain

    if domain not in config.get('domains', {}):
        print(f"Error: Domain '{domain}' not found in {args.config}")
        print(f"\nRun '{sys.argv[0]} --list' to see available domains.")
        sys.exit(1)

    # Get project settings
    settings = get_project_settings()

    # Load domain-specific settings from config first
    domain_config = config['domains'][domain]
    if 'settings' in domain_config:
        print(f"\nApplying domain-specific settings:")
        for key, value in domain_config['settings'].items():
            settings.set(key, value)
            print(f"  {key}: {value}")

    domain_state_dir = Path('.scrapy') / domain
    domain_state_dir.mkdir(parents=True, exist_ok=True)
    settings.set('JOBDIR', str(domain_state_dir), priority='spider')

    # Apply custom settings from command line (these override domain settings)
    if args.set:
        print(f"\nApplying command-line overrides:")
        for setting in args.set:
            if '=' not in setting:
                print(f"Warning: Invalid setting format '{setting}'. Use KEY=VALUE format.")
                continue
            key, value = setting.split('=', 1)
            settings.set(key, value)
            print(f"  {key}: {value}")

    # Set output format if specified
    if args.output:
        settings.set('FEEDS', {
            args.output: {'format': 'jsonlines'}
        })
        print(f"\nOutput will be written to: {args.output}")

    # Create crawler process
    process = CrawlerProcess(settings)

    print(f"\nStarting crawler for domain: {domain}")
    print("-" * 80)

    # Crawl single domain
    process.crawl(
        UniversalSpider,
        domain=domain,
        config_file=args.config
    )

    # Start crawling
    process.start()


if __name__ == '__main__':
    main()