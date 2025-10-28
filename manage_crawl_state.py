#!/usr/bin/env python3
"""
Command-line tool to inspect and manage crawl state for bigdata spider.

Usage:
    python manage_crawl_state.py list
    python manage_crawl_state.py stats veganchef.com
    python manage_crawl_state.py failed botanical.com --limit 50
    python manage_crawl_state.py reset homebnc
    python manage_crawl_state.py clear thriftyfun.com
    python manage_crawl_state.py export-failed veganchef.com --output failed.txt
"""

import argparse
import sqlite3
import sys
from pathlib import Path
import json


class CrawlStateManager:
    """Manage crawl state database"""

    def __init__(self, state_dir='crawl_state'):
        self.state_dir = Path(state_dir)
        if not self.state_dir.exists():
            print(f"State directory '{state_dir}' not found. No crawls have been run yet.")
            sys.exit(1)

    def get_db_path(self, domain):
        """Get database path for domain"""
        db_path = self.state_dir / f'{domain}_state.db'
        if not db_path.exists():
            print(f"Error: No state database found for domain '{domain}'")
            print(f"Expected: {db_path}")
            sys.exit(1)
        return db_path

    def list_domains(self):
        """List all domains with state databases"""
        print("\n" + "=" * 80)
        print("Available Crawl States")
        print("=" * 80)

        domains = []
        for db_file in sorted(self.state_dir.glob('*_state.db')):
            domain = db_file.stem.replace('_state', '')
            domains.append(domain)

            conn = sqlite3.connect(db_file)

            # Get stats
            cursor = conn.execute("""
                                  SELECT status, COUNT(*) as count
                                  FROM fingerprints
                                  WHERE domain = ?
                                  GROUP BY status
                                  """, (domain,))
            stats = dict(cursor.fetchall())

            # Get queue size
            cursor = conn.execute("""
                                  SELECT COUNT(*)
                                  FROM request_queue
                                  WHERE domain = ?
                                  """, (domain,))
            queue_size = cursor.fetchone()[0]

            # Get last activity
            cursor = conn.execute("""
                                  SELECT MAX(last_seen)
                                  FROM fingerprints
                                  WHERE domain = ?
                                  """, (domain,))
            last_activity = cursor.fetchone()[0]

            conn.close()

            success = stats.get('success', 0)
            failed = stats.get('failed', 0)
            pending = stats.get('pending', 0)
            total = sum(stats.values())

            print(f"\n📊 {domain}")
            print(f"   Database: {db_file.name}")
            print(f"   Success: {success:,} | Failed: {failed:,} | Pending: {pending:,} | Total: {total:,}")
            print(f"   Queue: {queue_size:,} requests")
            if last_activity:
                print(f"   Last activity: {last_activity}")

        if not domains:
            print("\n No domains found. Run some crawls first!")

        print("\n" + "=" * 80)

    def show_stats(self, domain):
        """Show detailed statistics for a domain"""
        db_path = self.get_db_path(domain)
        conn = sqlite3.connect(db_path)

        print("\n" + "=" * 80)
        print(f"📊 Crawl Statistics: {domain}")
        print("=" * 80)

        # Overall stats
        cursor = conn.execute("""
                              SELECT status, COUNT(*) as count
                              FROM fingerprints
                              WHERE domain = ?
                              GROUP BY status
                              """, (domain,))

        stats = dict(cursor.fetchall())
        total = sum(stats.values())
        success = stats.get('success', 0)
        failed = stats.get('failed', 0)
        pending = stats.get('pending', 0)

        if total > 0:
            print(f"\n📈 Overall Statistics:")
            print(f"   Total URLs seen: {total:,}")
            print(f"   ✅ Successfully crawled: {success:,} ({success / total * 100:.1f}%)")
            print(f"   ❌ Failed: {failed:,} ({failed / total * 100:.1f}%)")
            print(f"   ⏳ Still pending: {pending:,} ({pending / total * 100:.1f}%)")

        # Queue stats
        cursor = conn.execute("""
                              SELECT COUNT(*)
                              FROM request_queue
                              WHERE domain = ?
                              """, (domain,))
        queue_size = cursor.fetchone()[0]
        print(f"\n📥 Request Queue:")
        print(f"   Pending in queue: {queue_size:,}")

        # HTTP status breakdown for failed
        cursor = conn.execute("""
                              SELECT http_status, COUNT(*) as count
                              FROM fingerprints
                              WHERE domain = ? AND status = 'failed' AND http_status IS NOT NULL
                              GROUP BY http_status
                              ORDER BY count DESC
                              """, (domain,))

        http_stats = cursor.fetchall()
        if http_stats:
            print(f"\n🔴 Failed URLs by HTTP Status:")
            for http_status, count in http_stats:
                print(f"   HTTP {http_status}: {count:,} URLs")

        # Retry stats
        cursor = conn.execute("""
                              SELECT retry_count, COUNT(*) as count
                              FROM fingerprints
                              WHERE domain = ? AND status = 'failed'
                              GROUP BY retry_count
                              ORDER BY retry_count
                              """, (domain,))

        retry_stats = cursor.fetchall()
        if retry_stats:
            print(f"\n🔄 Failed URLs by Retry Count:")
            for retry_count, count in retry_stats:
                print(f"   {retry_count} retries: {count:,} URLs")

        # Recent activity
        cursor = conn.execute("""
                              SELECT
                                  DATE (last_seen) as date, status, COUNT (*) as count
                              FROM fingerprints
                              WHERE domain = ?
                              GROUP BY DATE (last_seen), status
                              ORDER BY date DESC
                                  LIMIT 14
                              """, (domain,))

        recent = cursor.fetchall()
        if recent:
            print(f"\n📅 Recent Activity (last 14 days):")
            current_date = None
            for date, status, count in recent:
                if date != current_date:
                    if current_date is not None:
                        print()
                    print(f"   {date}:")
                    current_date = date
                emoji = "✅" if status == "success" else "❌" if status == "failed" else "⏳"
                print(f"     {emoji} {status}: {count:,}")

        conn.close()
        print("\n" + "=" * 80)

    def show_failed(self, domain, limit=50):
        """Show failed URLs"""
        db_path = self.get_db_path(domain)
        conn = sqlite3.connect(db_path)

        cursor = conn.execute("""
                              SELECT url, retry_count, http_status, last_seen
                              FROM fingerprints
                              WHERE domain = ? AND status = 'failed'
                              ORDER BY last_seen DESC
                                  LIMIT ?
                              """, (domain, limit))

        failed = cursor.fetchall()
        conn.close()

        if not failed:
            print(f"\n✅ No failed URLs found for {domain}")
            return

        print("\n" + "=" * 80)
        print(f"❌ Failed URLs: {domain} (showing top {len(failed)})")
        print("=" * 80)

        for url, retry_count, http_status, last_seen in failed:
            status_str = f"HTTP {http_status}" if http_status else "Error"
            print(f"\n🔗 {url}")
            print(f"   {status_str} | Retries: {retry_count} | Last: {last_seen}")

        print("\n" + "=" * 80)

    def export_failed(self, domain, output_path):
        """Export failed URLs to file"""
        db_path = self.get_db_path(domain)
        conn = sqlite3.connect(db_path)

        cursor = conn.execute("""
                              SELECT url, retry_count, http_status, last_seen
                              FROM fingerprints
                              WHERE domain = ? AND status = 'failed'
                              ORDER BY last_seen DESC
                              """, (domain,))

        failed = cursor.fetchall()
        conn.close()

        if not failed:
            print(f"\n✅ No failed URLs to export for {domain}")
            return

        output_path = Path(output_path)

        if output_path.suffix == '.json':
            data = [
                {
                    'url': url,
                    'retry_count': retry_count,
                    'http_status': http_status,
                    'last_seen': last_seen
                }
                for url, retry_count, http_status, last_seen in failed
            ]
            with open(output_path, 'w') as f:
                json.dump(data, f, indent=2)
        else:
            # Plain text, one URL per line
            with open(output_path, 'w') as f:
                for url, _, _, _ in failed:
                    f.write(f"{url}\n")

        print(f"\n✅ Exported {len(failed):,} failed URLs to: {output_path}")

    def reset_failed(self, domain):
        """Reset failed URLs to allow recrawling"""
        db_path = self.get_db_path(domain)
        conn = sqlite3.connect(db_path)

        # Count failed URLs
        cursor = conn.execute("""
                              SELECT COUNT(*)
                              FROM fingerprints
                              WHERE domain = ? AND status = 'failed'
                              """, (domain,))
        count = cursor.fetchone()[0]

        if count == 0:
            print(f"\n✅ No failed URLs to reset for {domain}")
            conn.close()
            return

        # Confirm action
        print(f"\n⚠️  This will reset {count:,} failed URLs for {domain}")
        print(f"   They will be marked as pending and retried on next crawl.")
        response = input("\nContinue? (yes/no): ")

        if response.lower() != 'yes':
            print("❌ Aborted.")
            conn.close()
            return

        # Reset failed URLs
        conn.execute("""
                     UPDATE fingerprints
                     SET status      = 'pending',
                         retry_count = 0
                     WHERE domain = ? AND status = 'failed'
                     """, (domain,))
        conn.commit()
        conn.close()

        print(f"\n✅ Reset {count:,} failed URLs. They will be retried on next crawl.")
        print(f"   Run: python run.py {domain}")

    def clear_domain(self, domain):
        """Clear all state for a domain"""
        db_path = self.get_db_path(domain)

        # Get stats first
        conn = sqlite3.connect(db_path)
        cursor = conn.execute("""
                              SELECT COUNT(*)
                              FROM fingerprints
                              WHERE domain = ?
                              """, (domain,))
        total_urls = cursor.fetchone()[0]
        conn.close()

        # Confirm action
        print(f"\n⚠️  WARNING: This will DELETE ALL crawl state for {domain}")
        print(f"   Database: {db_path}")
        print(f"   Total URLs in database: {total_urls:,}")
        print(f"\n   Next crawl will start completely fresh (from scratch).")
        response = input(f"\nType '{domain}' to confirm deletion: ")

        if response != domain:
            print("❌ Aborted.")
            return

        db_path.unlink()
        print(f"\n✅ Deleted all state for {domain}")
        print(f"   Next crawl will start from the beginning.")


def main():
    parser = argparse.ArgumentParser(
        description='Manage Scrapy crawl state for bigdata spider',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s list                              # List all domains
  %(prog)s stats veganchef.com               # Show detailed stats
  %(prog)s failed botanical.com --limit 100  # Show failed URLs
  %(prog)s export-failed veganchef.com --output failed.txt
  %(prog)s reset homebnc                     # Reset failed URLs to retry
  %(prog)s clear thriftyfun.com              # Delete all state

Use Cases:
  - Resume interrupted crawls (automatic with SCHEDULER_PERSIST=True)
  - Retry failed URLs after fixing issues (reset command)
  - Monitor crawl progress (stats command)
  - Export failed URLs for analysis (export-failed command)
        """
    )

    parser.add_argument(
        'command',
        choices=['list', 'stats', 'failed', 'export-failed', 'reset', 'clear'],
        help='Command to execute'
    )

    parser.add_argument(
        'domain',
        nargs='?',
        help='Domain name (e.g., veganchef.com)'
    )

    parser.add_argument(
        '--state-dir',
        default='crawl_state',
        help='Path to crawl state directory (default: crawl_state)'
    )

    parser.add_argument(
        '--limit',
        type=int,
        default=50,
        help='Limit number of results (for failed command)'
    )

    parser.add_argument(
        '--output',
        help='Output file path (for export-failed command)'
    )

    args = parser.parse_args()

    # Validate arguments
    if args.command in ['stats', 'failed', 'export-failed', 'reset', 'clear'] and not args.domain:
        parser.error(f"{args.command} command requires domain argument")

    if args.command == 'export-failed' and not args.output:
        parser.error("export-failed command requires --output argument")

    # Execute command
    manager = CrawlStateManager(args.state_dir)

    if args.command == 'list':
        manager.list_domains()
    elif args.command == 'stats':
        manager.show_stats(args.domain)
    elif args.command == 'failed':
        manager.show_failed(args.domain, args.limit)
    elif args.command == 'export-failed':
        manager.export_failed(args.domain, args.output)
    elif args.command == 'reset':
        manager.reset_failed(args.domain)
    elif args.command == 'clear':
        manager.clear_domain(args.domain)


if __name__ == '__main__':
    main()