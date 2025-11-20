#!/usr/bin/env python3
"""
Site Noise Analyzer - Pass 1
Analyzes WordPress sites to detect repetitive noise and generate XPath pruning rules
"""

import json
import argparse
import logging
from pathlib import Path
from typing import Dict, List, Tuple, Set
from collections import Counter, defaultdict
from dataclasses import dataclass, asdict
import random
import sys
from multiprocessing import cpu_count

try:
    from lxml import html as lxml_html, etree
    from tqdm.auto import tqdm
except ImportError:
    print("ERROR: Install dependencies:")
    print("pip install lxml tqdm")
    sys.exit(1)


# ============================================================================
# CONFIGURATION
# ============================================================================

@dataclass
class AnalyzerConfig:
    """Analyzer configuration"""
    noise_threshold: float = 0.70  # 70% of articles must have this text
    min_text_length: int = 5  # Minimum chars to consider (short UI strings)
    max_text_length: int = 500  # Maximum chars (avoid matching full articles)
    sample_size: int = 5000  # Random sample size
    process_all: bool = False  # Process all articles instead of sampling
    edge_zone_percent: float = 0.20  # First/last 20% of content = higher noise probability
    min_articles_required: int = 10  # Minimum articles needed to analyze a site


# ============================================================================
# TEXT BLOCK EXTRACTOR
# ============================================================================

class TextBlockExtractor:
    """Extract meaningful text blocks from HTML with position tracking"""

    @staticmethod
    def extract_blocks(html: str, url: str = '') -> List[Dict]:
        """
        Extract text blocks with metadata
        Returns: [{text, xpath, position, context, element_type}]
        """
        if not html:
            return []

        try:
            doc = lxml_html.fromstring(html)
        except:
            return []

        blocks = []

        # Get all text-bearing elements
        # Expanded focus to include anchors, buttons, emphasis, and headings to catch CTAs
        text_elements = doc.xpath(
            './/*[self::p or self::div or self::span or self::li or self::td or self::th or self::aside or self::header or self::footer or self::nav or self::section or self::a or self::button or self::em or self::strong or self::h1 or self::h2 or self::h3 or self::h4 or self::h5 or self::h6]')

        total_elements = len(text_elements)

        for idx, elem in enumerate(text_elements):
            # Get full text including children for accurate block capture
            text = ' '.join(elem.itertext()).strip()

            # Lowered min length to catch short CTAs like "Read more", "Subscribe", etc.
            if not text or len(text) < 5:
                continue

            # Calculate position (0.0 = start, 1.0 = end)
            position = idx / total_elements if total_elements > 0 else 0.5

            # Generate XPath
            xpath = TextBlockExtractor._generate_xpath(elem)

            # Get element context
            context = {
                'tag': elem.tag,
                'classes': elem.get('class', '').split(),
                'id': elem.get('id', ''),
                'has_links': len(elem.xpath('.//a')) > 0,
                'has_images': len(elem.xpath('.//img')) > 0,
            }

            blocks.append({
                'text': text,
                'xpath': xpath,
                'position': position,
                'context': context,
                'url': url
            })

        return blocks

    @staticmethod
    def _generate_xpath(elem) -> str:
        """
        Generate the best XPath for an element
        Priority: ID > Class > Semantic tag > Positional
        """
        # Try ID first (most specific)
        elem_id = elem.get('id')
        if elem_id:
            return f"//{elem.tag}[@id='{elem_id}']"

        # Try class-based (good reusability)
        elem_class = elem.get('class', '').strip()
        if elem_class:
            # Use first class or most semantic class and match multi-class via contains()
            classes = elem_class.split()
            best_class = TextBlockExtractor._pick_best_class(classes)
            if best_class:
                return f"//{elem.tag}[contains(concat(' ', normalize-space(@class), ' '), ' {best_class} ')]"

        # Try semantic parent with class
        parent = elem.getparent()
        if parent is not None:
            parent_class = parent.get('class', '').strip()
            if parent_class:
                classes = parent_class.split()
                best_class = TextBlockExtractor._pick_best_class(classes)
                if best_class:
                    return f"//{parent.tag}[contains(concat(' ', normalize-space(@class), ' '), ' {best_class} ')]//{elem.tag}"

        # Fallback to semantic tag patterns
        if elem.tag in ['header', 'footer', 'aside', 'nav']:
            return f"//{elem.tag}"

        # Last resort: contains text pattern (less precise but works)
        text_snippet = (''.join(elem.itertext()) if elem is not None else '')[:30].strip()
        if text_snippet:
            # Use proper quoting for XPath contains()
            if "'" in text_snippet and '"' in text_snippet:
                # Fallback: drop snippet if both quotes present to avoid complex concat
                pass
            elif "'" in text_snippet:
                return f'//{elem.tag}[contains(text(), "{text_snippet}")]'
            else:
                return f"//{elem.tag}[contains(text(), '{text_snippet}')]"

        return None

    @staticmethod
    def _pick_best_class(classes: List[str]) -> str:
        """Pick the most semantic/meaningful class"""
        # Prioritize noise-indicating classes
        noise_keywords = [
            'header', 'footer', 'nav', 'sidebar', 'widget',
            'social', 'share', 'newsletter', 'subscribe', 'follow',
            'related', 'author', 'bio', 'meta', 'breadcrumb',
            'comment', 'ad', 'ads', 'promo', 'banner', 'cta', 'btn', 'button',
            'affiliate', 'sponsored', 'disclosure', 'cookie', 'gdpr', 'toc', 'table-of-contents',
            'readmore', 'read-more', 'also-read', 'print-recipe', 'youtube', 'pinterest', 'facebook', 'twitter', 'instagram'
        ]

        for cls in classes:
            cls_lower = cls.lower()
            if any(kw in cls_lower for kw in noise_keywords):
                return cls

        # Return first class if no semantic match
        return classes[0] if classes else None


# ============================================================================
# NOISE DETECTOR
# ============================================================================

class NoiseDetector:
    """Detect repetitive noise patterns across articles"""

    def __init__(self, config: AnalyzerConfig):
        self.config = config
        # Common CTA/boilerplate indicators used to relax thresholds when detected
        self.cta_keywords = [
            'read more', 'readmore', 'read also', 'also read', 'recommended', 'you may also like',
            'subscribe', 'newsletter', 'sign up', 'sign-up', 'join our', 'get updates',
            'follow me', 'follow us', 'follow on', 'share this', 'share on',
            'pinterest', 'facebook', 'twitter', 'x.com', 'instagram', 'tiktok', 'youtube', 'linkedin',
            'download', 'get the app', 'buy now', 'shop now', 'add to cart', 'order now',
            'disclosure', 'affiliate', 'sponsored', 'ad disclosure', 'as an amazon associate',
            'terms of use', 'privacy policy', 'cookie policy', 'gdpr',
            'author bio', 'about the author', 'leave a comment', 'comments are closed',
            'similar posts', 'related posts', 'related articles', 'related content',
            'watch on youtube', 'watch the video', 'print recipe', 'table of contents', 'toc'
        ]

    def _contains_cta(self, text: str) -> bool:
        tl = (text or '').lower()
        return any(k in tl for k in self.cta_keywords)

    def analyze_site(self, articles: List[Dict]) -> Dict:
        """
        Analyze all articles from a site
        Returns: {
            'repetitive_blocks': [...],
            'suggested_xpaths': [...],
            'stats': {...}
        }
        """
        if len(articles) < self.config.min_articles_required:
            return {
                'repetitive_blocks': [],
                'suggested_xpaths': [],
                'stats': {'reason': 'insufficient_articles', 'count': len(articles)}
            }

        # Extract blocks from all articles
        all_blocks = []
        for article in articles:
            blocks = TextBlockExtractor.extract_blocks(
                article['html'],
                article['url']
            )
            all_blocks.extend(blocks)

        if not all_blocks:
            return {
                'repetitive_blocks': [],
                'suggested_xpaths': [],
                'stats': {
                    'reason': 'no_blocks_extracted',
                    'total_articles': len(articles),
                    'total_blocks': 0
                }
            }

        # Find repetitive text patterns
        repetitive = self._find_repetitive_patterns(all_blocks, len(articles))

        # Generate XPath rules
        xpaths = self._generate_xpath_rules(repetitive)

        # Build detailed report
        report = {
            'repetitive_blocks': repetitive,
            'suggested_xpaths': xpaths,
            'stats': {
                'total_articles': len(articles),
                'total_blocks': len(all_blocks),
                'repetitive_patterns': len(repetitive),
                'suggested_xpaths': len(xpaths)
            }
        }

        return report

    def _find_repetitive_patterns(self, blocks: List[Dict], total_articles: int) -> List[Dict]:
        """Find text patterns that repeat across articles (text-based + structure-based)"""

        # Group by normalized text
        text_groups = defaultdict(list)
        # Group by XPath (structure-based)
        xpath_groups = defaultdict(list)

        for block in blocks:
            # Track xpath groups regardless of text match
            xp = block.get('xpath')
            if xp:
                xpath_groups[xp].append(block)

            # Normalize text for matching
            normalized = self._normalize_text(block['text'])

            # Filter by length for text-based grouping
            if len(normalized) < self.config.min_text_length:
                continue
            if len(normalized) > self.config.max_text_length:
                continue

            text_groups[normalized].append(block)

        # Find patterns above threshold (text-based)
        base_threshold_count = max(2, int(total_articles * self.config.noise_threshold))
        repetitive = []
        seen_xpaths: Set[str] = set()

        for text, occurrences in text_groups.items():
            # Count unique articles (not just occurrences)
            unique_urls = len(set(b['url'] for b in occurrences))

            # Relax threshold if CTA-like
            contains_cta = any(self._contains_cta(b.get('text','')) for b in occurrences)
            threshold_count = max(3, int(total_articles * (0.30 if contains_cta else self.config.noise_threshold)))

            if unique_urls >= threshold_count:
                # Calculate noise score
                noise_score = self._calculate_noise_score(occurrences, total_articles)

                # Get representative block
                representative = occurrences[0]
                xp = representative.get('xpath')
                if xp:
                    seen_xpaths.add(xp)

                repetitive.append({
                    'text': text[:200],  # Truncate for display
                    'full_text': text,
                    'frequency': unique_urls,
                    'frequency_percent': (unique_urls / total_articles) * 100,
                    'noise_score': noise_score,
                    'xpath': xp,
                    'position_avg': sum(b['position'] for b in occurrences) / len(occurrences),
                    'sample_urls': list(set(b['url'] for b in occurrences))[:5],
                    'context': representative['context']
                })

        # Structure-based detection by XPath frequency across unique articles
        noise_tags = {'header', 'footer', 'aside', 'nav', 'button'}
        noise_class_keywords = [
            'social', 'share', 'newsletter', 'subscribe', 'follow',
            'related', 'author', 'meta', 'comment', 'ad', 'promo', 'breadcrumb',
            'affiliate', 'sponsored', 'disclosure', 'cookie', 'gdpr', 'toc', 'table-of-contents',
            'readmore', 'read-more', 'also-read', 'cta', 'btn', 'button', 'print-recipe', 'youtube'
        ]
        for xp, occs in xpath_groups.items():
            # Compute unique-URL coverage
            unique_urls = len(set(b['url'] for b in occs))
            if unique_urls < 2:
                continue

            # Derive context factors
            ctx_samples = [b.get('context') or {} for b in occs if b.get('context')]
            tag_points = 0
            class_points = 0
            for ctx in ctx_samples[:10]:  # sample a few for speed
                tag = (ctx.get('tag') or '').lower()
                if tag in noise_tags:
                    tag_points += 1
                cls_str = ' '.join((ctx.get('classes') or [])).lower()
                if any(kw in cls_str for kw in noise_class_keywords):
                    class_points += 1

            # Position: average
            pos_avg = sum(b['position'] for b in occs) / max(1, len(occs))
            edge_bonus = 1 if (pos_avg < self.config.edge_zone_percent or pos_avg > (1 - self.config.edge_zone_percent)) else 0

            # Adjust threshold down if strong noise signals
            adj_threshold = self.config.noise_threshold
            if tag_points > 0:
                adj_threshold = min(adj_threshold, 0.40)  # headers/footers are highly repetitive but vary in text
            if class_points > 0 or edge_bonus:
                adj_threshold = min(adj_threshold, 0.50)

            # If CTA-like wording appears within this XPath group, relax further
            try:
                cta_like = False
                for b in occs[:50]:  # sample up to 50 blocks for speed
                    t = (b.get('text') or '')
                    if self._contains_cta(t):
                        cta_like = True
                        break
                if cta_like:
                    adj_threshold = min(adj_threshold, 0.30)
            except Exception:
                pass

            needed = max(2, int(total_articles * adj_threshold))
            if unique_urls >= needed:
                # Skip if we already reported the same xpath via text-based
                if xp in seen_xpaths:
                    continue

                # Choose a representative text: most common short text within bounds
                texts = []
                for b in occs:
                    t = self._normalize_text(b['text'])
                    if t and self.config.min_text_length <= len(t) <= self.config.max_text_length:
                        texts.append(t)
                rep_text = ''
                if texts:
                    cnt = Counter(texts)
                    rep_text = next(iter(cnt.most_common(1)))[0]
                else:
                    # fallback to first 200 chars raw
                    rep_text = (occs[0]['text'] or '')[:200]

                # Build occurrences for scoring (reuse occs)
                noise_score = self._calculate_noise_score(occs, total_articles)

                repetitive.append({
                    'text': rep_text[:200],
                    'full_text': rep_text,
                    'frequency': unique_urls,
                    'frequency_percent': (unique_urls / total_articles) * 100,
                    'noise_score': noise_score,
                    'xpath': xp,
                    'position_avg': pos_avg,
                    'sample_urls': list(set(b['url'] for b in occs))[:5],
                    'context': occs[0].get('context') or {}
                })

        # Sort by noise score (highest first)
        repetitive.sort(key=lambda x: x['noise_score'], reverse=True)

        return repetitive

    def _normalize_text(self, text: str) -> str:
        """Normalize text for comparison"""
        import re

        # Convert to lowercase
        text = text.lower()

        # Remove extra whitespace
        text = ' '.join(text.split())

        # Remove numbers (dates, years, etc vary but pattern is same)
        text = re.sub(r'\d+', '', text)

        # Remove common variable parts
        text = re.sub(r'(january|february|march|april|may|june|july|august|september|october|november|december)',
                      'MONTH', text)
        text = re.sub(r'(monday|tuesday|wednesday|thursday|friday|saturday|sunday)', 'DAY', text)

        return text.strip()

    def _calculate_noise_score(self, occurrences: List[Dict], total_articles: int) -> float:
        """
        Calculate noise score (0-100)
        Higher = more likely to be noise
        """
        score = 0.0

        # Factor 1: Frequency (0-40 points)
        unique_urls = len(set(b['url'] for b in occurrences))
        frequency_score = (unique_urls / total_articles) * 40
        score += frequency_score

        # Factor 2: Position (0-30 points)
        # Text at edges is more likely noise
        avg_position = sum(b['position'] for b in occurrences) / len(occurrences)
        if avg_position < self.config.edge_zone_percent:
            position_score = 30  # Top noise
        elif avg_position > (1 - self.config.edge_zone_percent):
            position_score = 30  # Bottom noise
        else:
            position_score = 0  # Middle = likely content
        score += position_score

        # Factor 3: Context (0-30 points)
        context = occurrences[0]['context']
        context_score = 0

        # Noise tags
        if context['tag'] in ['header', 'footer', 'aside', 'nav']:
            context_score += 15

        # Noise classes
        noise_class_keywords = [
            'social', 'share', 'newsletter', 'subscribe',
            'related', 'author', 'meta', 'comment', 'ad', 'promo'
        ]
        classes_str = ' '.join(context['classes']).lower()
        if any(kw in classes_str for kw in noise_class_keywords):
            context_score += 15

        score += context_score

        return min(score, 100.0)

    def _generate_xpath_rules(self, repetitive_blocks: List[Dict]) -> List[Dict]:
        """Generate XPath pruning rules from repetitive blocks"""

        xpath_rules = []
        seen_xpaths = set()

        for block in repetitive_blocks:
            xpath = block['xpath']

            if not xpath or xpath in seen_xpaths:
                continue

            seen_xpaths.add(xpath)

            xpath_rules.append({
                'xpath': xpath,
                'reason': f"Appears in {block['frequency']} articles ({block['frequency_percent']:.1f}%)",
                'sample_text': block['text'],
                'noise_score': block['noise_score'],
                'sample_urls': block['sample_urls']
            })

        return xpath_rules


# ============================================================================
# MAIN ANALYZER
# ============================================================================

class SiteNoiseAnalyzer:
    """Main analyzer orchestrator"""

    def __init__(self, config: AnalyzerConfig):
        self.config = config
        self.detector = NoiseDetector(config)

    def _analyze_single_file(self, input_file: Path) -> Tuple[str, Dict, Counter]:
        """Analyze one file and return site_key, result, and xpath counter"""
        site_key = input_file.stem
        print(f"\nAnalyzing: {site_key}")

        # Load articles
        articles = self._load_articles(input_file)
        if not articles:
            print(f"  ✗ No articles found")
            return site_key, {
                'repetitive_blocks': [],
                'suggested_xpaths': [],
                'stats': {'reason': 'no_articles', 'total_articles': 0, 'total_blocks': 0}
            }, Counter()

        print(f"  Loaded {len(articles)} articles")

        # Sample if needed
        if not self.config.process_all and len(articles) > self.config.sample_size:
            articles = random.sample(articles, self.config.sample_size)
            print(f"  Sampled {len(articles)} articles")

        # Analyze
        result = self.detector.analyze_site(articles)

        # Debug: print why no patterns detected
        if 'stats' in result and 'reason' in result['stats']:
            print(f"  ✗ No noise patterns detected: {result['stats']['reason']}")
        elif not result['suggested_xpaths']:
            print(f"  ✗ No noise patterns detected")
            print(f"     Debug: {result['stats']}")
        else:
            print(f"  ✓ Found {len(result['suggested_xpaths'])} noise patterns")

        # Accumulate global XPaths
        xpath_counter = Counter()
        for xpath_rule in result['suggested_xpaths']:
            if xpath_rule and xpath_rule.get('xpath'):
                xpath_counter[xpath_rule['xpath']] += 1

        return site_key, result, xpath_counter

    def analyze_files(self, input_dir: Path, workers: int = None) -> Dict:
        """Analyze all JSONL files in directory using parallel workers"""

        input_files = sorted(input_dir.glob('*.jsonl'))

        if not input_files:
            print(f"ERROR: No .jsonl files in {input_dir}")
            return {}

        print(f"\n{'=' * 70}")
        print(f"NOISE ANALYZER - Pass 1")
        print(f"{'=' * 70}")
        print(f"Files: {len(input_files)}")
        print(f"Sampling: {'ALL' if self.config.process_all else f'{self.config.sample_size} per file'}")
        print(f"Noise threshold: {self.config.noise_threshold * 100}%")
        print(f"{'=' * 70}\n")

        all_results = {
            'global_xpaths': [],
            'flattened_xpaths': [],
            'site_specific': {},
            'stats': {
                'total_files': len(input_files),
                'total_articles_analyzed': 0,
                'total_noise_patterns': 0
            }
        }

        global_xpath_counter = Counter()

        # Parallel processing per file
        from concurrent.futures import ProcessPoolExecutor, as_completed
        max_workers = workers or min(len(input_files), max(1, cpu_count() // 2))
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(SiteNoiseAnalyzer._analyze_file_static, file, self.config): file for file in input_files}
            for future in as_completed(futures):
                site_key, result, xpath_counter = future.result()
                all_results['site_specific'][site_key] = result
                all_results['stats']['total_articles_analyzed'] += result['stats'].get('total_articles', 0)
                all_results['stats']['total_noise_patterns'] += len(result['repetitive_blocks'])
                global_xpath_counter.update(xpath_counter)

        # Build global XPath list (appears in multiple sites)
        global_xpaths = []
        for xpath, count in global_xpath_counter.most_common():
            if count >= 2:  # Appears in 2+ sites
                global_xpaths.append({
                    'xpath': xpath,
                    'appears_in_sites': count,
                    'reason': f'Common pattern across {count} sites'
                })

        all_results['global_xpaths'] = global_xpaths
        all_results['stats']['global_patterns'] = len(global_xpaths)

        # Flattened list for cleaner consumption: site-specific union with global
        flat = set(x['xpath'] for x in global_xpaths)
        for site_data in all_results['site_specific'].values():
            for xr in site_data.get('suggested_xpaths') or []:
                xp = xr.get('xpath')
                if xp:
                    flat.add(xp)
        all_results['flattened_xpaths'] = [{'xpath': xp} for xp in sorted(flat)]

        return all_results

    @staticmethod
    def _analyze_file_static(input_file: Path, config: AnalyzerConfig) -> Tuple[str, Dict, Counter]:
        analyzer = SiteNoiseAnalyzer(config)
        return analyzer._analyze_single_file(input_file)

    def _load_articles(self, filepath: Path) -> List[Dict]:
        """Load articles from JSONL file"""
        articles = []

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue

                    try:
                        # Parse the line
                        record = json.loads(line)

                        # Extract URL
                        url = record.get('url', '')

                        # Parse body field (it's a JSON STRING!)
                        body_raw = record.get('body', '{}')
                        if isinstance(body_raw, str):
                            try:
                                body = json.loads(body_raw)
                            except:
                                logging.debug(f"Failed to parse body JSON for {url}")
                                continue
                        else:
                            body = body_raw

                        # Get content HTML from WordPress REST response
                        content_raw = body.get('content', {})
                        if isinstance(content_raw, dict):
                            html = content_raw.get('rendered', '')
                        else:
                            html = str(content_raw) if content_raw else ''

                        if html and len(html) > 100:
                            articles.append({
                                'url': url,
                                'html': html
                            })
                        else:
                            logging.debug(f"Skipping article {url} - empty or too short HTML")

                    except json.JSONDecodeError as e:
                        logging.debug(f"JSON parse error: {e}")
                        continue
                    except Exception as e:
                        logging.debug(f"Parse error: {e}")
                        continue

        except Exception as e:
            logging.error(f"File read error: {e}")

        return articles


# ============================================================================
# OUTPUT GENERATOR
# ============================================================================

def save_results(results: Dict, output_file: Path):
    """Save analysis results to JSON"""

    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\n{'=' * 70}")
    print(f"ANALYSIS COMPLETE")
    print(f"{'=' * 70}")
    print(f"Output saved to: {output_file}")
    print(f"\nSummary:")
    print(f"  Sites analyzed: {results['stats']['total_files']}")
    print(f"  Articles analyzed: {results['stats']['total_articles_analyzed']}")
    print(f"  Total noise patterns: {results['stats']['total_noise_patterns']}")
    print(f"  Global patterns: {results['stats']['global_patterns']}")
    print(f"\nReview the output file and remove any false positives before cleaning.")
    print(f"{'=' * 70}\n")


def generate_human_readable_report(results: Dict, output_file: Path):
    """Generate human-readable report for verification"""

    report_file = output_file.parent / f"{output_file.stem}_report.txt"

    with open(report_file, 'w', encoding='utf-8') as f:
        f.write("=" * 70 + "\n")
        f.write("NOISE ANALYSIS REPORT\n")
        f.write("=" * 70 + "\n\n")

        # Global patterns
        f.write("GLOBAL PATTERNS (appears in multiple sites):\n")
        f.write("-" * 70 + "\n")
        for xpath_info in results['global_xpaths']:
            f.write(f"\nXPath: {xpath_info['xpath']}\n")
            f.write(f"Appears in: {xpath_info['appears_in_sites']} sites\n")

        f.write("\n\n")

        # Site-specific patterns
        for site_key, site_data in results['site_specific'].items():
            f.write("=" * 70 + "\n")
            f.write(f"SITE: {site_key}\n")
            f.write("=" * 70 + "\n\n")

            f.write(f"Articles analyzed: {site_data['stats']['total_articles']}\n")
            f.write(f"Noise patterns found: {len(site_data['repetitive_blocks'])}\n\n")

            for idx, block in enumerate(site_data['repetitive_blocks'][:20], 1):  # Top 20
                f.write(f"\n--- Pattern #{idx} (Noise Score: {block['noise_score']:.1f}) ---\n")
                f.write(f"Frequency: {block['frequency']} articles ({block['frequency_percent']:.1f}%)\n")
                f.write(f"XPath: {block['xpath']}\n")
                f.write(f"Sample text: {block['text']}\n")
                f.write(f"Sample URLs:\n")
                for url in block['sample_urls']:
                    f.write(f"  - {url}\n")

            f.write("\n")

    print(f"Human-readable report: {report_file}")


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description='Analyze WordPress sites to detect noise patterns',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )

    parser.add_argument('-i', '--input-dir', type=str, required=True,
                        help='Input directory with JSONL files')
    parser.add_argument('-o', '--output', type=str, default='noise_config.json',
                        help='Output JSON file (default: noise_config.json)')
    parser.add_argument('-s', '--sample-size', type=int, default=5000,
                        help='Sample size per file (default: 5000)')
    parser.add_argument('-a', '--process-all', action='store_true',
                        help='Process all articles (no sampling)')
    parser.add_argument('-t', '--threshold', type=float, default=0.70,
                        help='Noise threshold 0-1 (default: 0.70)')
    parser.add_argument('--min-length', type=int, default=5,
                        help='Minimum text length (default: 5)')
    parser.add_argument('--max-length', type=int, default=500,
                        help='Maximum text length (default: 500)')
    parser.add_argument('-w', '--workers', type=int, default=max(1, cpu_count() // 2),
                        help='Parallel workers (default: half of CPU cores)')

    args = parser.parse_args()

    config = AnalyzerConfig(
        noise_threshold=args.threshold,
        min_text_length=args.min_length,
        max_text_length=args.max_length,
        sample_size=args.sample_size,
        process_all=args.process_all
    )

    analyzer = SiteNoiseAnalyzer(config)

    results = analyzer.analyze_files(Path(args.input_dir), workers=args.workers)

    if results:
        output_path = Path(args.output)
        save_results(results, output_path)
        generate_human_readable_report(results, output_path)


if __name__ == '__main__':
    main()