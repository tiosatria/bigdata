import json
import re
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from multiprocessing import Pool, cpu_count
import time
from functools import partial  # Import partial

# ============================================================================
# CONFIGURATION SECTION
# ============================================================================
# Numbered list patterns - actionable vs non-actionable
ACTIONABLE_NUMBERED_PATTERNS = [
    r'^\d+\s+(ways?|tips?|tricks?|hacks?|methods?|techniques?|steps?|recipes?|ideas?)\s+',
    r'^\d+\s+(how to|to)',
    r'^\d+\s+diy\s+',
    r'^\d+\s+(simple|easy|quick|practical|useful|essential)\s+',
    r'^\d+\s+.+\s+(topping|ingredient|substitut|alternative|option)',
    r''
]
NON_ACTIONABLE_NUMBERED_PATTERNS = [
    r'^\d+\s+best\s+.+\s+(of\s+\d{4}|movies?|films?|games?|shows?|albums?)',
    r'^\d+\s+(reasons?|facts?|things?)\s+(why|about|to know)',
    r'^\d+\s+(celebrities?|stars?|actors?)',
    r'^\d+\s+most\s+(expensive|popular|watched|controversial)',
]
INCLUSION_KEYWORDS = [
    # Action words
    r'\bhow to\b',
    r'\btips?\b',
    r'\btricks?\b',
    r'\bhacks?\b',
    r'\bguides?\b',
    r'\bways? to\b',
    r'\bsteps? to\b',
    r'\bmethods?\b',
    r'\btechniques?\b',
    r'\badvice\b',
    r'\binstructions?\b',

    # Practical actions
    r'\bmake\b',
    r'\bcook\b',
    r'\bprepare\b',
    r'\bclean\b',
    r'\borganize\b',
    r'\bstore\b',
    r'\bremove\b',
    r'\bfix\b',
    r'\brepair\b',
    r'\bcreate\b',
    r'\bbuild\b',
    r'\bcraft\b',

    r'\bmaster\b',

    # Specific domains
    r'\brecipes?\b',
    r'\bdiy\b',
    r'\bhomemade\b',
    r'\bhandmade\b',
    r'\bnatural remedy\b',
    r'\bhome remedy\b',
    r'\btopping\b',
    r'\bingredient\b',

    r'\bideas?\b',
    r'\binnovations?\b',
    r'\bremed(y|ies)?\b',
]
EXCLUSION_START_PATTERNS = [
    r'^who\b',
    r'^watch\b',
    # r'^what\b',
    r'^when\b',
    # r'^why\b',
    r'^where\b',
    # r'^which\b',
    r'^breaking\b',
    r'^news:',
    r'^live:',
    r'^review:',
    r'^opinion:',
    r'^debate:',
    r'^buy\b',
    r'^purchase\b',
    r'^deal:',
    r'^sale:',
    r'^survey'
]
EXCLUSION_KEYWORDS = [
    # News/Media
    'breaking news',
    'live stream',
    'watch now',
    'latest news',
    'just in',
    'developing',
    'update:',
    'breaking:',
    'stupid',
    'funny',
    'dumb',
    'memes',
    'photo',
    # Marketing/Promotional
    'subscribe',
    'follow us',
    'click here',
    'advertisement',
    'sponsored',
    'affiliate',
    'partner',
    'promotion',
    'discount code',
    'coupon',
    'giveaway',
    'contest',
    # Product/Business News
    'unboxing',
    'first look',
    'hands-on',
    'versus',
    r'\bvs\.?\b',
    'comparison',
    'launches',
    'announces',
    'announcement',
    'unveils',
    'reveals',
    'introduces',
    'release date',
    'coming soon',
    'available now',
    'pre-order',
    'expansion',
    'new location',
    'opens',
    'opening',
    'closes',
    'closing',
    'acquisition',
    'merger',
    'partnership',
    # Entertainment/Media
    'celebrity',
    'entertainment',
    'series',
    'episode',
    'season',
    'trailer',
    'teaser',
    'premiere',
    'red carpet',
    'award',
    'nominee',
    'winner',
    # Gaming
    'gameplay',
    'walkthrough',
    'playthrough',
    "let's play",
    'gaming',
    'esports',
    'tournament',
    'minecraft',
    'casino',
    # Sports
    'sports',
    'match',
    'score',
    'playoff',
    'championship',
    'league',
    'athlete',
    # Politics/Controversial
    'politics',
    'political',
    'election',
    'vote',
    'campaign',
    'candidate',
    'controversy',
    'controversial',
    'scandal',
    'protest',
    # Gossip/Rumors
    'rumors',
    'rumor',
    'leaked',
    'leak',
    'insider',
    'source says',
    'allegedly',
    'drama',
    # Interviews/Opinion
    'interview',
    'exclusive interview',
    'talks about',
    'speaks out',
    'shares thoughts',
    'opinion',
    'my take',
    'hot take',
    'unpopular opinion',
    # Lists/Rankings (often not actionable)
    r'\bbest of \d{4}',
    r'\btop \d+',
    r'\b\d+ best',
    r'\bworst \d+',
    'ranking',
    'ranked',
    'tier list',
    # Time-sensitive content
    r'\b20\d{2}\b',  # Years 2000-2099
    'this week',
    'this month',
    'this year',
    'yesterday',
    'tomorrow',
    r'\bgif\b'
]
EXCLUSION_URL_PATTERNS = [
    r'/news/',
    # r'/entertainment/',
    # r'/sports/',
    r'/politics/',
    r'/celebrity/',
    r'/review/',
    r'/reviews/',
    r'/opinion/',
    r'/video/',
    r'/watch/',
    r'/gallery/',
    r'/slideshow/',
    r'/photos/',
]
# ============================================================================
# FILTERING FUNCTIONS
# ============================================================================
def normalize_text(text):
    """Normalize text for matching."""
    if not text:
        return ""
    return text.lower().strip()

def check_inclusion(title, url):
    """Check if content has at least one inclusion keyword."""
    combined = f"{normalize_text(title)} {normalize_text(url)}"

    for pattern in INCLUSION_KEYWORDS:
        if re.search(pattern, combined, re.IGNORECASE):
            return True, f"Matches inclusion: {pattern}"

    return False, "No actionable/practical keywords found"

def check_exclusion(title, url):
    """Check if title or URL matches exclusion patterns."""
    title_norm = normalize_text(title)
    url_norm = normalize_text(url)

    # Check title start patterns
    for pattern in EXCLUSION_START_PATTERNS:
        if re.search(pattern, title_norm, re.IGNORECASE):
            return True, f"Excluded start pattern: {pattern}"
    # Check exclusion keywords
    combined = f"{title_norm} {url_norm}"
    for keyword in EXCLUSION_KEYWORDS:
        if isinstance(keyword, str):
            if keyword.lower() in combined:
                return True, f"Excluded keyword: {keyword}"
        else:  # regex pattern
            if re.search(keyword, combined, re.IGNORECASE):
                return True, f"Excluded keyword pattern: {keyword}"
    # Check URL patterns
    for pattern in EXCLUSION_URL_PATTERNS:
        if re.search(pattern, url_norm, re.IGNORECASE):
            return True, f"Excluded URL pattern: {pattern}"
    return False, None

def is_relevant(title, url):
    """
    Determine if content is relevant.
    Returns (is_relevant, reason)
    """
    title_norm = normalize_text(title)

    # First check exclusions (faster)
    is_excluded, reason = check_exclusion(title, url)
    if is_excluded:
        return False, reason

    # Special handling for numbered titles
    if re.match(r'^\d+\s+', title_norm):
        # Check if it's non-actionable numbered list
        for pattern in NON_ACTIONABLE_NUMBERED_PATTERNS:
            if re.search(pattern, title_norm, re.IGNORECASE):
                return False, f"Non-actionable numbered list: {pattern}"

        # Check if it's actionable numbered list
        for pattern in ACTIONABLE_NUMBERED_PATTERNS:
            if re.search(pattern, title_norm, re.IGNORECASE):
                return True, f"Actionable numbered list: {pattern}"

    # Then check if it has actionable content
    has_inclusion, reason = check_inclusion(title, url)
    if not has_inclusion:
        return False, reason
    return True, "Passed all filters"

# ============================================================================
# PROCESSING FUNCTIONS (REWRITTEN)
# ============================================================================

def process_line(line):
    """
    Process a single line (JSON string).
    This function is run by worker processes.
    """
    try:
        data = json.loads(line.strip())
        # Extract fields
        title = data.get('meta', {}).get('data_info', {}).get('title', '')
        url = data.get('meta', {}).get('data_info', {}).get('url', '')
        # Check relevance
        relevant, reason = is_relevant(title, url)
        if relevant:
            return ('accepted', data, reason)
        else:
            # Add rejection reason
            data['_rejection_reason'] = reason
            return ('rejected', data, reason)
    except (json.JSONDecodeError, Exception):
        # Silently ignore bad lines
        return None

def process_file_parallel(input_path, output_dir, num_workers):
    """
    Process a single JSONL file using streaming and a worker pool.
    """
    filename = Path(input_path).name
    base_name = Path(input_path).stem

    # Output paths
    accepted_path = output_dir / 'accepted' / f"{base_name}_accepted.jsonl"
    rejected_path = output_dir / 'rejected' / f"{base_name}_rejected.jsonl"

    accepted_path.parent.mkdir(parents=True, exist_ok=True)
    rejected_path.parent.mkdir(parents=True, exist_ok=True)

    # Statistics
    stats = {
        'filename': filename,
        'total': 0,
        'accepted': 0,
        'rejected': 0,
        'errors': 0,
        'rejection_reasons': defaultdict(int),
        'subdomains': defaultdict(int),
        'sample_rejected': [],
    }

    print(f"\n{'=' * 80}")
    print(f"Processing: {filename}")
    print(f"Workers: {num_workers}")
    print(f"{'=' * 80}")

    start_process = time.time()
    try:
        # Use functools.partial to "fix" the domain argument for the worker
        # This way, process_line only needs to accept `line` from the pool
        worker_func = partial(process_line)

        # Open all files at once.
        # The input file `f_in` will be read as an iterable
        # The output files will be written to as results come in
        with open(input_path, 'r', encoding='utf-8') as f_in, \
                open(accepted_path, 'w', encoding='utf-8') as accepted_file, \
                open(rejected_path, 'w', encoding='utf-8') as rejected_file, \
                Pool(processes=num_workers) as pool:

            print(f"Streaming and processing with {num_workers} workers...")

            # Set a chunksize for imap_unordered. This is NOT lines, but
            # how many tasks to send to a worker at once.
            # A value like 500-1000 is good.
            chunksize = 2000

            # Use imap_unordered to process the file iterable (f_in)
            # This reads from f_in, sends chunks to workers,
            # and yields results as they are completed (out of order).
            results_iterator = pool.imap_unordered(worker_func, f_in, chunksize)

            # Process results as they come in (streaming)
            for result in results_iterator:
                stats['total'] += 1

                if not result:
                    stats['errors'] += 1
                    continue

                result_type, data, reason = result

                if result_type == 'accepted':
                    accepted_file.write(json.dumps(data, ensure_ascii=False) + '\n')
                    stats['accepted'] += 1
                else:  # 'rejected'
                    rejected_file.write(json.dumps(data, ensure_ascii=False) + '\n')
                    stats['rejected'] += 1
                    stats['rejection_reasons'][reason] += 1

                    if len(stats['sample_rejected']) < 10:
                        title = data.get('meta', {}).get('data_info', {}).get('title', '')
                        stats['sample_rejected'].append(f"{title} | {reason}")

                # Optional: Add a progress indicator
                if stats['total'] % 1000 == 0:
                    print(f"  ... processed {stats['total']:,} lines", end='\r')

        # End of 'with' block, files are closed
        process_time = time.time() - start_process
        speed = stats['total'] / process_time if process_time > 0 else 0

        print(f"\n✓ Completed in {process_time:.2f}s ({speed:.0f} lines/sec)")
        if stats['errors'] > 0:
            print(f"  (Ignored {stats['errors']:,} bad lines/errors)")

        return stats, str(accepted_path), str(rejected_path)

    except Exception as e:
        print(f"❌ ERROR: {str(e)}")
        return {'error': str(e), 'filename': str(input_path)}, None, None


# ============================================================================
# MAIN & STATISTICS
# ============================================================================

def print_statistics(filename, stats):
    """Print detailed statistics for a file."""
    if 'error' in stats:
        print(f"\n❌ ERROR processing {stats['filename']}: {stats['error']}")
        return

    print(f"\n{'=' * 80}")
    print(f"RESULTS: {filename}")
    print(f"{'=' * 80}")
    print(f"Total entries:        {stats['total']:,}")
    print(f"✓ Accepted:          {stats['accepted']:,} ({stats['accepted'] / stats['total'] * 100:.2f}%)")
    print(f"✗ Rejected:          {stats['rejected']:,} ({stats['rejected'] / stats['total'] * 100:.2f}%)")
    if stats['errors'] > 0:
        print(f"  Errors/Bad Lines:   {stats['errors']:,}")

    if stats['subdomains']:
        print(f"\n{'-' * 80}")
        print("Subdomain Distribution (Accepted Content):")
        print(f"{'-' * 80}")
        for subdomain, count in sorted(stats['subdomains'].items(), key=lambda x: x[1], reverse=True):
            pct = count / stats['accepted'] * 100 if stats['accepted'] > 0 else 0
            print(f"  {subdomain:30} {count:>6,} ({pct:>5.1f}%)")

    if stats['rejection_reasons']:
        print(f"\n{'-' * 80}")
        print("Top Rejection Reasons:")
        print(f"{'-' * 80}")
        for reason, count in sorted(stats['rejection_reasons'].items(), key=lambda x: x[1], reverse=True)[:10]:
            pct = count / stats['rejected'] * 100 if stats['rejected'] > 0 else 0
            print(f"  {count:>6,} ({pct:>5.1f}%) - {reason}")

    if stats['sample_rejected']:
        print(f"\n{'-' * 80}")
        print("Sample Rejected Titles:")
        print(f"{'-' * 80}")
        for i, sample in enumerate(stats['sample_rejected'], 1):
            print(f"  {i}. {sample}")


def main():
    """Main processing function with multiprocessing per file."""
    import argparse

    parser = argparse.ArgumentParser(description='Filter daily life corpus data (Multi-core per file)')
    parser.add_argument('input_dir', help='Input directory containing JSONL files')
    parser.add_argument('output_dir', help='Output directory for filtered files')
    parser.add_argument('--file', help='Process specific file only (optional)')
    parser.add_argument('--workers', type=int, default=None, help='Number of worker processes (default: CPU count)')

    args = parser.parse_args()

    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    # Create output directory
    output_dir.mkdir(parents=True, exist_ok=True)

    # Get list of files to process
    if args.file:
        files = [input_dir / args.file]
    else:
        files = sorted(input_dir.glob('*.jsonl'))

    if not files:
        print(" No JSONL files found!")
        return

    # Determine number of workers
    num_workers = args.workers if args.workers else cpu_count()

    print(f"\n{'=' * 80}")
    print(f"CORPUS FILTERING - Daily Life Content (Multi-core per file)")
    print(f"{'=' * 80}")
    print(f"Input directory:  {input_dir}")
    print(f"Output directory: {output_dir}")
    print(f"Files to process: {len(files)}")
    print(f"CPU cores:        {cpu_count()}")
    print(f"Workers per file: {num_workers}")
    print(f"{'=' * 80}\n")

    # Process files sequentially, but use all cores per file
    total_stats = {
        'files': 0,
        'total': 0,
        'accepted': 0,
        'rejected': 0,
    }

    start_time = datetime.now()

    print(f"🚀 Starting parallel processing with {num_workers} workers per file...\n")

    for file_path in files:
        stats, accepted_path, rejected_path = process_file_parallel(file_path, output_dir, num_workers)

        if 'error' not in stats:
            print_statistics(file_path.name, stats)
            total_stats['files'] += 1
            total_stats['total'] += stats['total']
            total_stats['accepted'] += stats['accepted']
            total_stats['rejected'] += stats['rejected']
        else:
            print(f"\nERROR: {stats['filename']} - {stats['error']}")

    # Print overall statistics
    elapsed = datetime.now() - start_time

    print(f"\n{'=' * 80}")
    print("FINAL SUMMARY")
    print(f"{'=' * 80}")
    print(f"Files processed:      {total_stats['files']:,}")
    print(f"Total entries:        {total_stats['total']:,}")
    if total_stats['total'] > 0:
        print(
            f"✓ Total accepted:    {total_stats['accepted']:,} ({total_stats['accepted'] / total_stats['total'] * 100:.2f}%)")
        print(
            f"✗ Total rejected:    {total_stats['rejected']:,} ({total_stats['rejected'] / total_stats['total'] * 100:.2f}%)")
    print(f"Processing time:      {elapsed}")
    if elapsed.total_seconds() > 0:
        print(f"Speed:                {total_stats['total'] / elapsed.total_seconds():.0f} entries/second")
    print(f"\n📁 Output saved to: {output_dir}")
    print(f"{'=' * 80}\n")

if __name__ == '__main__':
    main()