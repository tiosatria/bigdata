import requests
import gzip
from bs4 import BeautifulSoup
import csv
from urllib.parse import urlparse
from collections import defaultdict
import time
import argparse
import json


class CommonCrawlWordPressExtractor:
    def __init__(self):
        self.cc_indexes = []
        self.results = []

    def get_cc_index_list(self):
        """Get list of available Common Crawl indexes"""
        try:
            response = requests.get("https://index.commoncrawl.org/collinfo.json", timeout=10)
            if response.status_code == 200:
                data = response.json()
                # Get latest indexes
                return [item['id'] for item in data[:10]]
        except Exception as e:
            print(f"Error fetching index list: {e}")

        # Fallback to known indexes
        return [
            "CC-MAIN-2024-38",
            "CC-MAIN-2024-33",
            "CC-MAIN-2024-30",
        ]

    def search_index(self, index_name, url_pattern, filters=None, limit=1000):
        """Search a specific Common Crawl index"""
        api_url = f"https://index.commoncrawl.org/{index_name}-index"

        params = {
            'url': url_pattern,
            'output': 'json',
        }

        # Add filters if provided
        if filters:
            for f in filters:
                params['filter'] = f

        results = []
        try:
            response = requests.get(api_url, params=params, timeout=30)

            if response.status_code == 200:
                lines = response.text.strip().split('\n')
                count = 0
                for line in lines:
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        results.append(data)
                        count += 1
                        if count >= limit:
                            break
                    except:
                        continue

        except Exception as e:
            print(f"    Error querying: {e}")

        return results

    def is_valid_url(self, url):
        """Check if URL is valid and not a resource file"""
        try:
            parsed = urlparse(url)
            skip_extensions = [
                '.css', '.js', '.jpg', '.png', '.gif', '.svg', '.woff', '.ttf',
                '.jpeg', '.ico', '.webp', '.mp4', '.pdf', '.zip', '.xml',
                'robots.txt', 'sitemap.xml', 'favicon.ico', 'ads.txt',
                '.json', '.txt', '.woff2', '.eot'
            ]
            url_lower = url.lower()

            if parsed.scheme not in ['http', 'https']:
                return False

            # Skip resource files
            if any(url_lower.endswith(ext) or f'/{ext}' in url_lower for ext in skip_extensions):
                return False

            # Skip main wordpress.com
            if parsed.netloc == 'wordpress.com' or parsed.netloc == 'www.wordpress.com':
                return False

            return True
        except:
            return False

    def fetch_page_content(self, warc_record):
        """Fetch the actual page content from WARC file"""
        try:
            filename = warc_record.get('filename')
            offset = int(warc_record.get('offset', 0))
            length = int(warc_record.get('length', 0))

            if not filename or not length:
                return None

            warc_url = f"https://data.commoncrawl.org/{filename}"
            headers = {'Range': f'bytes={offset}-{offset + length - 1}'}
            response = requests.get(warc_url, headers=headers, timeout=15)

            if response.status_code == 206:
                try:
                    content = gzip.decompress(response.content).decode('utf-8', errors='ignore')
                    parts = content.split('\r\n\r\n')
                    if len(parts) >= 3:
                        return parts[-1]
                except:
                    pass

        except Exception as e:
            pass
        return None

    def is_wordpress_from_html(self, html):
        """Detect WordPress from HTML content"""
        if not html or len(html) < 100:
            return False

        html_lower = html.lower()

        # Strong WordPress indicators
        strong_indicators = [
            'wp-content/themes/',
            'wp-content/plugins/',
            'wp-includes/',
            '/wp-json/',
            'wp-embed',
            'powered by wordpress',
            'wordpress.com',
        ]

        indicator_count = sum(1 for indicator in strong_indicators if indicator in html_lower)
        return indicator_count >= 2

    def analyze_site(self, url, html):
        """Analyze a WordPress site and extract metadata"""
        try:
            soup = BeautifulSoup(html, 'html.parser')

            title_tag = soup.find('title')
            title = title_tag.get_text().strip() if title_tag else urlparse(url).netloc
            title = title[:200]

            desc_tag = soup.find('meta', attrs={'name': 'description'}) or \
                       soup.find('meta', attrs={'property': 'og:description'})
            description = desc_tag.get('content', '').strip() if desc_tag else ''

            if not description:
                p_tag = soup.find('p')
                if p_tag:
                    description = p_tag.get_text().strip()[:200]

            description = description[:500]

            category = self.categorize_site(title, description, html[:3000])

            return {
                'url': url,
                'domain': urlparse(url).netloc,
                'title': title,
                'description': description,
                'category': category
            }
        except:
            return None

    def categorize_site(self, title, description, html_snippet):
        """Categorize the website based on content"""
        text = f"{title} {description} {html_snippet}".lower()

        categories = {
            'Sports': ['sport', 'football', 'basketball', 'soccer', 'tennis', 'fitness',
                       'athlete', 'game', 'team', 'championship', 'league', 'player'],
            'Cooking/Food': ['cook', 'recipe', 'food', 'kitchen', 'meal', 'dish', 'cuisine',
                             'ingredient', 'chef', 'baking', 'restaurant'],
            'Lifestyle': ['lifestyle', 'daily', 'living', 'home', 'family', 'parenting',
                          'wellness', 'self-care', 'routine', 'tips', 'advice'],
            'Technology': ['tech', 'software', 'computer', 'programming', 'digital',
                           'app', 'gadget', 'code', 'developer', 'data'],
            'Business': ['business', 'entrepreneur', 'startup', 'finance', 'marketing',
                         'corporate', 'management', 'investment'],
            'Health': ['health', 'medical', 'wellness', 'fitness', 'nutrition',
                       'medicine', 'therapy', 'healthcare', 'diet'],
            'Travel': ['travel', 'tourism', 'destination', 'vacation', 'trip', 'journey',
                       'hotel', 'flight', 'explore'],
            'Education': ['education', 'learning', 'school', 'course', 'teaching',
                          'tutorial', 'training', 'university', 'study'],
            'Entertainment': ['entertainment', 'movie', 'music', 'celebrity', 'show',
                              'concert', 'tv', 'video'],
            'News/Media': ['news', 'article', 'report', 'journalism', 'breaking',
                           'press', 'media', 'story'],
            'Fashion/Beauty': ['fashion', 'style', 'beauty', 'clothing', 'makeup',
                               'trend', 'outfit'],
            'Finance': ['finance', 'money', 'investment', 'trading', 'stock',
                        'banking', 'wealth', 'crypto'],
        }

        scores = defaultdict(int)
        for category, keywords in categories.items():
            for keyword in keywords:
                count = text.count(keyword)
                # Weight title mentions higher
                if keyword in title.lower():
                    count *= 3
                scores[category] += count

        if scores:
            return max(scores.items(), key=lambda x: x[1])[0]
        return 'General/Other'

    def extract_wordpress_sites(self, min_sites=50, check_content=True):
        """Extract WordPress sites from Common Crawl"""
        print("Fetching available Common Crawl indexes...")
        indexes = self.get_cc_index_list()
        print(f"Will search through {len(indexes)} indexes\n")

        wordpress_sites = []
        seen_domains = set()
        checked_count = 0

        for index in indexes:
            if len(wordpress_sites) >= min_sites:
                break

            print(f"\n{'=' * 70}")
            print(f"Searching index: {index}")
            print('=' * 70)

            # Strategy: search for wordpress.com subdomains
            print(f"\nSearching for *.wordpress.com sites...")
            url_pattern = '*.wordpress.com'
            filters = ['=status:200', '=mime:text/html']

            records = self.search_index(index, url_pattern, filters, limit=500)
            print(f"  Found {len(records)} records to process")

            for record in records:
                if len(wordpress_sites) >= min_sites:
                    break

                url = record.get('url', '')

                if not self.is_valid_url(url):
                    continue

                parsed = urlparse(url)
                domain = parsed.netloc

                if domain in seen_domains:
                    continue

                checked_count += 1

                if checked_count % 25 == 0:
                    print(f"  Progress: Checked {checked_count}, Found {len(wordpress_sites)} WordPress sites")

                if check_content:
                    html = self.fetch_page_content(record)

                    if html and self.is_wordpress_from_html(html):
                        site_info = self.analyze_site(url, html)
                        if site_info:
                            seen_domains.add(domain)
                            wordpress_sites.append(site_info)
                            print(f"  ✓ {len(wordpress_sites)}. {domain} [{site_info['category']}]")
                else:
                    # Quick mode
                    seen_domains.add(domain)
                    base_url = f"{parsed.scheme}://{domain}"
                    site_info = {
                        'url': base_url,
                        'domain': domain,
                        'title': domain,
                        'description': 'WordPress.com hosted site',
                        'category': 'Unknown'
                    }
                    wordpress_sites.append(site_info)
                    print(f"  + {len(wordpress_sites)}. {domain}")

            time.sleep(2)

        print(f"\n\n{'=' * 70}")
        print(f"Search complete! Found {len(wordpress_sites)} unique WordPress sites")
        print('=' * 70)

        return wordpress_sites

    def export_to_csv(self, sites, filename='wordpress_sites.csv'):
        """Export results to CSV"""
        if not sites:
            print("No sites to export!")
            return

        with open(filename, 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['domain', 'url', 'title', 'description', 'category'])
            writer.writeheader()
            writer.writerows(sites)

        print(f"\n✓ Exported {len(sites)} sites to {filename}")

        categories = {}
        for site in sites:
            cat = site['category']
            categories[cat] = categories.get(cat, 0) + 1

        print("\n📊 Category breakdown:")
        for cat, count in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            print(f"  {cat}: {count}")


def main():
    parser = argparse.ArgumentParser(description='Extract WordPress sites from Common Crawl')
    parser.add_argument('-n', '--min-sites', type=int, default=50,
                        help='Minimum number of sites to find before exiting (default: 50)')
    parser.add_argument('--quick', action='store_true',
                        help='Quick mode: skip content verification (faster)')
    parser.add_argument('-o', '--output', type=str, default='wordpress_sites.csv',
                        help='Output CSV filename (default: wordpress_sites.csv)')

    args = parser.parse_args()

    print("=" * 70)
    print("WordPress Site Extractor from Common Crawl")
    print("=" * 70)
    print(f"Target: {args.min_sites} unique WordPress sites")
    print(f"Mode: {'Quick (no verification)' if args.quick else 'Full verification'}")
    print(f"Output: {args.output}")
    print("=" * 70)

    extractor = CommonCrawlWordPressExtractor()

    sites = extractor.extract_wordpress_sites(
        min_sites=args.min_sites,
        check_content=not args.quick
    )

    if sites:
        extractor.export_to_csv(sites, args.output)
    else:
        print("\n❌ No WordPress sites found.")


if __name__ == "__main__":
    main()