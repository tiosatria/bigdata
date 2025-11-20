import json
import re
import os
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from multiprocessing import Pool, cpu_count
import time
import argparse  # Import argparse here

# ============================================================================
# CONFIGURATION SECTION - REUSED FILTER LOGIC
# ============================================================================

# Numbered list patterns - actionable
ACTIONABLE_NUMBERED_PATTERNS = [
    r'^\d+\s+(ways?|tips?|tricks?|hacks?|methods?|techniques?|steps?|recipes?|ideas?|solutions?|uses?)\s+',
    r'^\d+\s+(how to|to)',
    r'^\d+\s+diy\s+',
    r'^\d+\s+(simple|easy|quick|practical|useful|essential)\s+',
    r'^\d+\s+.+\s+(substitute[s]?|alternative[s]?|option[s]?)',
    r'^\d+\s+uses?\s+for\s+', # e.g., "10 Uses for Vinegar"
]

# Numbered list patterns - non-actionable
NON_ACTIONABLE_NUMBERED_PATTERNS = [
    r'^\d+\s+best\s+.+\s+(of\s+\d{4}|movies?|films?|games?|shows?|albums?|songs?|books?|podcasts?|cars?)',
    r'^\d+\s+(reasons?|facts?|things?)\s+(why|about|to know|you didn\'t know|to remember)',
    r'^\d+\s+(celebrities?|stars?|actors?|athletes?)',
    r'^\d+\s+most\s+(expensive|popular|watched|controversial|beautiful|haunted|powerful)',
    r'^\d+\s+(trends?|quotes?|moments?|questions?)',
]

# Inclusion keywords - content MUST have at least one of these
# Inclusion keywords - content MUST have at least one of these
INCLUSION_KEYWORDS = [
    # Action words (Original)
    r'\bhow to\b', r'\btips?\b', r'\btricks?\b', r'\bhacks?\b', r'\bguides?\b',
    r'\bways? to\b', r'\bsteps? to\b', r'\bmethods?\b', r'\btechniques?\b',
    r'\badvice\b', r'\binstructions?\b',

    # Practical actions (Original)
    r'\bmake\b', r'\bcook\b', r'\bprepare\b', r'\bclean\b', r'\borganize\b',
    r'\bstore\b', r'\bremove\b', r'\bfix\b', r'\brepair\b', r'\bcreate\b',
    r'\bbuild\b', r'\bcraft\b',

    # Specific domains (Original)
    r'\brecipes?\b', r'\bdiy\b', r'\bhomemade\b', r'\bhandmade\b',
    r'\bnatural remedy\b', r'\bhome remedy\b', r'\btopping\b', r'\bingredient\b',

    # --- NEWLY ADDED TO INCREASE RECALL ---

    # Home Care & Cleaning
    r'\bstain removal\b', r'\borganizing\b', r'\bdeclutter\b', r'\bstorage solution[s]?\b',
    r'\blaundry\b', r'\bpolishing\b', r'\bscrub\b', r'\bdisinfect\b',

    # Cooking/Food
    r'\bpreservation\b', r'\bfood storage\b', r'\bkitchen tips?\b', r'\bmeal prep\b',
    r'\bpreserve\b', r'\bcanning\b', r'\bfreezing\b', r'\bbaking\b',

    # Health/Personal Care
    r'\bpersonal care\b', r'\bwellness\b', r'\bskincare\b', r'\bhair care\b',
    r'\bnatural\b', r'\bremedies\b', r'\bsoothe\b', r'\btreatment[s]?\b',

    # DIY/Crafts
    r'\brepurpose\b', r'\bupcycle\b', r'\bcrafts\b', r'\bsewing\b', r'\bknitting\b',

    # Home Environment
    r'\bodor removal\b', r'\bdeodorize\b', r'\bfreshen\b', r'\bplant care\b', r'\bgardening\b',

    # Food Substitutes
    r'\bsubstitute[s]?\b', r'\balternative[s]?\b', r'\ballergy-friendly\b',
    r'\bgluten-free\b', r'\bdairy-free\b', r'\bvegan\b',
]

# Exclusion patterns - titles starting with these
# Exclusion patterns - titles starting with these (MUCH more relaxed)
EXCLUSION_START_PATTERNS = [
    # 'who' is almost always about people/celebs, so it's safe to block
    r'^who\b',
    r'^watch\b',
    r'^news:',
    r'^live:',
    r'^review:',  # 'Review' is not actionable, safe to block
    r'^opinion:',
    r'^debate:',
    r'^buy\b',
    r'^purchase\b',
    r'^deal:',
    r'^sale:',

    # r'^what\b',  <-- Too broad, blocks "What to do with..."
    # r'^when\b',  <-- Too broad, blocks "When to plant..."
    # r'^why\b',   <-- Too broad, blocks "Why you should..."
    # r'^where\b', <-- Too broad, blocks "Where to store..."
    # r'^which\b', <-- Too broad, blocks "Which apple is best for..."
]

# Exclusion keywords - if found anywhere in title
EXCLUSION_KEYWORDS = [
    # News/Media (Original)
    'breaking news', 'live stream', 'watch now', 'latest news', 'just in',
    'developing', 'update:',
    # Marketing/Promotional (Original)
    'subscribe', 'follow us', 'click here', 'advertisement', 'sponsored',
    'affiliate', 'partner', 'promotion', 'discount code', 'coupon', 'giveaway', 'contest',
    # Product/Business News (Original)
    'unboxing', 'first look', 'hands-on', 'versus',
    r'\bvs\.?\b',
    'comparison',
    'launches', 'announces', 'announcement', 'unveils', 'reveals', 'introduces',
    'release date', 'coming soon', 'available now', 'pre-order', 'expansion',
    'new location', 'opens', 'opening', 'closes', 'closing', 'acquisition',
    'merger', 'partnership',

    # Entertainment/Media (Original)
    'celebrity', 'entertainment', 'series', 'episode', 'season', 'trailer',
    'teaser', 'premiere', 'red carpet', 'award', 'nominee', 'winner',

    # Gaming (Original)
    'gameplay', 'walkthrough', 'playthrough', "let's play", 'gaming', 'esports', 'tournament',

    # Sports (Original)
    'sports', 'match', 'score', 'playoff', 'championship', 'league', 'athlete',

    # Politics/Controversial (Original)
    'politics', 'political', 'election', 'vote', 'campaign', 'candidate',
    'controversy', 'controversial', 'scandal', 'protest', 'policy', 'legislation',

    # Gossip/Rumors (Original)
    'rumors', 'rumor', 'leaked', 'leak', 'insider', 'source says', 'allegedly', 'drama',

    # Interviews/Opinion (Original)
    'interview', 'exclusive interview', 'talks about', 'speaks out', 'shares thoughts',
    'opinion', 'my take', 'hot take', 'unpopular opinion',

    # Lists/Rankings (Refined)
    'ranking', 'ranked', 'tier list',

    # --- REMOVED (Too broad, blocked good content) ---
    # r'\bbest of \d{4}', (Handled by NON_ACTIONABLE_NUMBERED_PATTERNS)
    # r'\btop \d+', (Blocks "Top 10 Tips...")
    # r'\b\d+ best', (Blocks "10 Best Ways to...")
    # r'\b20\d{2}\b', (Blocks "Gardening Tips for 2024")
    # 'this week', 'this month', 'this year', 'yesterday', 'tomorrow'

    # Finance/Business
    r'\bstock market\b', r'\binvesting\b', r'\bstocks?\b', r'\bcrypto\b', r'\bnft\b',
    r'\beconomy\b', r'\binflation\b', r'\bmortgage\b', r'\bloan[s]?\b', r'\bcredit card[s]?\b',
    r'\bfinance\b', r'\bfinancial\b', r'\bearnings\b',

    r'\bsmartphone\b', r'\blaptop\b', r'\bsoftware\b', r'\bapp[s]?\b', r'\b(app )?update\b',
    r'\bdata breach\b', r'\bstartup\b', r'\b(artificial intelligence|ai)\b',
    r'\btech\b', r'\btechnology\b', r'\bmetaverse\b',

    # Career/Work
    r'\bjob[s]?\b', r'\bresume\b', r'\binterview\b', r'\bsalary\b',
    r'\bworkplace\b', r'\bnetworking\b', r'\bcorporate\b',

    # Academics/Science (News, not actionable)
    r'\bcollege\b', r'\buniversity\b', r'\bresearch\b',
    r'\bscientific paper\b', r'\b(study|research) finds\b',

    # Legal
    r'\blaw\b', r'\blegal\b', r'\blawsuit\b', r'\bcourt\b', r'\bgovernment\b',
]

# URL exclusion patterns
EXCLUSION_URL_PATTERNS = [
    r'/news/',
    r'/entertainment/',
    r'/sports/',
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

    # --- NEWLY ADDED ---
    r'/business/',
    r'/finance/',
    r'/career/',
    r'/jobs/',
    r'/gaming/',
    r'/world/',
]


# ============================================================================
# FILTERING FUNCTIONS (UNCHANGED CORE LOGIC)
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
# PROCESSING FUNCTIONS (ADAPTED FOR NEW STRUCTURE)
# ============================================================================

def process_line(line):
    """
    Process a single line (JSON string) from the input file.
    This function is run by worker processes.
    """
    try:
        # 1. Parse the JSONL line
        data = json.loads(line.strip())

        # 2. Get top-level URL
        url = data.get('url', '')

        # 3. Get and parse the stringified body
        # This is the most fragile part
        body_str = data.get('body')
        body_data = json.loads(body_str)  # Fails on None/empty, caught by except

        # 4. Extract title from the parsed body
        title = body_data.get('title', {}).get('rendered', '')

        # 5. Run existing filter logic
        # is_relevant() will handle empty title/url and reject them
        relevant, reason = is_relevant(title, url)

        if relevant:
            # Return tuple for main process to handle
            return ('accepted', data, reason)
        else:
            # Add rejection reason
            data['_rejection_reason'] = reason
            return ('rejected', data, reason)

    except (json.JSONDecodeError, TypeError, AttributeError, Exception):
        # Catches:
        # - Bad outer JSON
        # - Missing 'body' field (AttributeError/TypeError on json.loads(None))
        # - Bad stringified JSON in 'body'
        # - Any other unexpected error
        # Silently ignore bad lines / processing errors, they'll be counted
        return None


def process_file_parallel(input_path, output_dir, num_workers):
    """
    Process a single JSONL file using streaming and a worker pool.
    """
    filename = Path(input_path).name
    base_name = Path(input_path).stem

    # Output paths
    accepted_path = output_dir / f"{base_name}_accepted.jsonl"
    rejected_path = output_dir / f"{base_name}_rejected.jsonl"

    # Statistics
    stats = {
        'filename': filename,
        'total': 0,
        'accepted': 0,
        'rejected': 0,
        'errors': 0,
        'rejection_reasons': defaultdict(int),
        'sample_rejected': [],
    }

    print(f"\n{'=' * 80}")
    print(f"Processing: {filename}")
    print(f"Workers: {num_workers}")
    print(f"{'=' * 80}")

    start_process = time.time()
    try:
        # Open all files at once.
        # The input file `f_in` will be read as an iterable
        # The output files will be written to as results come in
        with open(input_path, 'r', encoding='utf-8') as f_in, \
                open(accepted_path, 'w', encoding='utf-8') as accepted_file, \
                open(rejected_path, 'w', encoding='utf-8') as rejected_file, \
                Pool(processes=num_workers) as pool:

            print(f"Streaming and processing with {num_workers} workers...")

            # Set a chunksize for imap_unordered.
            chunksize = 1000

            # Use imap_unordered to process the file iterable (f_in)
            # No 'partial' is needed as process_line takes just one arg
            results_iterator = pool.imap_unordered(process_line, f_in, chunksize)

            # Process results as they come in (streaming)
            for result in results_iterator:
                stats['total'] += 1

                if not result:
                    stats['errors'] += 1
                    continue

                # Unpack the simpler tuple
                result_type, data, reason = result

                if result_type == 'accepted':
                    accepted_file.write(json.dumps(data, ensure_ascii=False) + '\n')
                    stats['accepted'] += 1
                else:  # 'rejected'
                    rejected_file.write(json.dumps(data, ensure_ascii=False) + '\n')
                    stats['rejected'] += 1
                    stats['rejection_reasons'][reason] += 1

                    if len(stats['sample_rejected']) < 10:
                        # Try to get title for logging, but don't fail
                        title_for_sample = "N/A"
                        try:
                            body_data = json.loads(data.get('body', '{}'))
                            title_for_sample = body_data.get('title', {}).get('rendered', 'N/A')
                        except Exception:
                            pass  # It's just for logging
                        stats['sample_rejected'].append(f"{title_for_sample} | {reason}")

                # Optional: Add a progress indicator
                if stats['total'] % 50000 == 0:
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
# MAIN & STATISTICS (SIMPLIFIED)
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
    if stats['total'] > 0:
        print(f"✓ Accepted:          {stats['accepted']:,} ({stats['accepted'] / stats['total'] * 100:.2f}%)")
        print(f"✗ Rejected:          {stats['rejected']:,} ({stats['rejected'] / stats['total'] * 100:.2f}%)")
    else:
        print("✓ Accepted:          0 (0.00%)")
        print("✗ Rejected:          0 (0.00%)")
    if stats['errors'] > 0:
        print(f"  Errors/Bad Lines:   {stats['errors']:,}")

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
    parser = argparse.ArgumentParser(description='Prefilter corpus data based on title/url (Multi-core per file)')
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
        print(f"❌ No JSONL files found in {input_dir}")
        return

    # Determine number of workers
    num_workers = args.workers if args.workers else cpu_count()

    print(f"\n{'=' * 80}")
    print(f"CORPUS PRE-FILTERING (Multi-core per file)")
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
            print(f"\n❌ ERROR: {stats['filename']} - {stats['error']}")

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