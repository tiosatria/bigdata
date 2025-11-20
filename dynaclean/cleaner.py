#!/usr/bin/env python3

"""
High-performance, parallel script for cleaning WordPress JSONL exports.

Version 2:
- Adds progress bar for line counting.
- Uses chunking for multiprocessing to increase CPU usage & throughput.
- Adds min_text_length and min_body_process filters.
- Fixes unicode escaping in output (ensure_ascii=False).

Input: JSONL
{
    "id": "guid",
    "url": "url",
    "meta": {"site": "example.com"},
    "body": "stringified json from wp-json/wp/v2/posts"
}

Output: JSONL
{
    "id": "guid",
    "text": "cleaned_title\ncleaned_body",
    "meta": {
        "data_info": {...},
        "content_info": {...}
    }
}
"""

import argparse
import os
import sys
import json
import re
import html
import logging
import uuid
import itertools
from datetime import datetime
from functools import partial
from multiprocessing import Pool, Manager, Process, Queue
from typing import Dict, Any, Optional, List
from queue import Empty
import time

# Third-party libraries
try:
    from lxml import html as lxml_html
    from lxml.etree import ParserError
    from lxml.html.clean import Cleaner
except ImportError:
    print("Error: 'lxml' library not found. Please install it: pip install lxml", file=sys.stderr)
    sys.exit(1)

try:
    from tqdm import tqdm
except ImportError:
    print("Error: 'tqdm' library not found. Please install it: pip install tqdm", file=sys.stderr)
    sys.exit(1)

# --- Anonymization Regexes (pre-compiled) ---
# Basic email regex
EMAIL_REGEX = re.compile(r'[\w\.-]+@[\w\.-]+\.\w+')
# Basic phone regex (intentionally broad to catch various formats)
PHONE_REGEX = re.compile(r'(\+?\d{1,3}[\s.-]?)?(\(?\d{3}\)?[\s.-]?)?[\d\s.-]{7,}')
# Basic social/sharing URL regex
SOCIAL_REGEX = re.compile(
    r'(https?://(www\.)?(twitter|facebook|linkedin|instagram|t\.me|wa\.me|x\.com)\.com?/[\w/\.-]+)')

# Emoji removal regex
EMOJI_REGEX = re.compile(
    "["
    "\U0001F600-\U0001F64F"  # emoticons
    "\U0001F300-\U0001F5FF"  # symbols & pictographs
    "\U0001F680-\U0001F6FF"  # transport & map symbols
    "\U0001F1E0-\U0001F1FF"  # flags (iOS)
    "\U00002700-\U000027BF"  # dingbats
    "\U00002600-\U000026FF"  # miscellaneous symbols
    "\U0001F900-\U0001F9FF"  # supplemental symbols and pictographs
    "\U0001FA70-\U0001FAFF"  # symbols and pictographs extended-A
    "\U00002B50"  # star
    "\U0000200D"  # zero width joiner
    "]+",
    flags=re.UNICODE)

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - [%(processName)s] - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
log = logging.getLogger()

def clean_title_func(title: str, remove_template: bool, clean_html:bool) -> str:
    """Cleans a title string."""
    if not title:
        return ""

    if clean_html:
        title = lxml_html.fromstring(title).text_content()

    # 1. Unescape HTML entities (e.g., &amp; -> &)
    cleaned = html.unescape(title)

    # 2. Remove site template (e.g., "My Post - My Site")
    if remove_template:
        # Matches a separator (with spaces) followed by text at the end.
        cleaned = re.sub(r'\s+([|\-–—])\s+.*$', '', cleaned, flags=re.IGNORECASE)

    # 3. Strip leading/trailing whitespace
    return cleaned.strip()


import re
from lxml import html as lxml_html
import logging

log = logging.getLogger(__name__)

def _convert_tables_to_latex(tree: lxml_html.HtmlElement):
    """
    Finds all <table> elements in the LXML tree and replaces them
    in-place with a LaTeX 'tabular' environment as text.
    """
    for table in tree.xpath('//table'):
        try:
            # Determine column count from the first row's cells (td or th)
            header_cells = table.xpath('.//tr[1]/*[self::td or self::th]')
            col_count = len(header_cells)
            if col_count == 0:
                # Try finding any cells if malformed HTML
                header_cells = table.xpath('.//tr/*[self::td or self::th]')
                col_count = len(header_cells)
                if col_count == 0:
                    table.drop_tree()
                    continue

            # Basic LaTeX structure (add | for borders)
            latex = [r'\begin{tabular}{|' + '|'.join(['l'] * col_count) + r'|}', r'\hline']

            for row in table.xpath('.//tr'):
                cells = row.xpath('./*[self::td or self::th]')
                cell_texts = []

                for cell in cells:
                    text = (cell.text_content() or "").strip()

                    # Proper order of escaping:
                    # 1. Escape backslashes first to avoid double escaping later
                    text = text.replace('\\', r'\textbackslash{}')
                    # 2. Escape special LaTeX characters
                    text = re.sub(r'([&%$#_{}])', r'\\\1', text)
                    # 3. Escape ^ and ~ which aren't caught by regex above
                    text = text.replace('^', r'\textasciicircum{}')
                    text = text.replace('~', r'\textasciitilde{}')

                    cell_texts.append(text)

                if cell_texts:
                    # Pad or truncate cells to match column count
                    if len(cell_texts) < col_count:
                        cell_texts.extend([''] * (col_count - len(cell_texts)))
                    elif len(cell_texts) > col_count:
                        cell_texts = cell_texts[:col_count]

                    latex.append(' & '.join(cell_texts) + r' \\ \hline')

            latex.append(r'\end{tabular}')
            latex_str = '\n'.join(latex) + '\n'

            # Replace the <table> node with a text node in its parent
            parent = table.getparent()
            if parent is not None:
                previous = table.getprevious()

                if previous is not None:
                    previous.tail = (previous.tail or '') + latex_str
                else:
                    parent.text = (parent.text or '') + latex_str

                # Append any trailing text after the table
                if table.tail:
                    if previous is not None:
                        previous.tail += table.tail
                    else:
                        parent.text = (parent.text or '') + table.tail

                table.drop_tree()

        except Exception as e:
            log.warning(f"Failed to convert table to LaTeX: {e}", exc_info=False)
            if table is not None and table.getparent() is not None:
                table.drop_tree()

import re
from urllib.parse import urlparse, urlunparse
from lxml import html as lxml_html
import logging

log = logging.getLogger(__name__)

def _convert_images_to_text(tree: lxml_html.HtmlElement):
    """
    Finds all <img> elements and replaces them in-place with
    [Image: {real image source link, fit size, not placeholder/svg}] text.
    """
    for img in tree.xpath('//img'):
        try:
            src = (img.get('data-src') or img.get('src') or '').strip()
            if not src:
                img.drop_tree()
                continue

            # Skip data URIs, SVGs, or known placeholder sources
            if src.startswith('data:') or src.lower().endswith('.svg') or 'placeholder' in src.lower():
                img.drop_tree()
                continue

            # Remove query params that are purely sizing (e.g. ?width=200, ?w=300)
            parsed = urlparse(src)
            query_clean = re.sub(r'(\b(w|width|h|height|size|fit)=\d+&?)+', '', parsed.query, flags=re.I)
            query_clean = query_clean.strip('&?')
            src_clean = urlunparse(parsed._replace(query=query_clean))

            # Build the output text
            replacement_text = f'[Image: {src_clean}\\]'

            # Insert in parent
            parent = img.getparent()
            if parent is not None:
                previous = img.getprevious()

                if previous is not None:
                    previous.tail = (previous.tail or '') + replacement_text
                else:
                    parent.text = (parent.text or '') + replacement_text

                # Preserve any trailing text after the <img>
                if img.tail:
                    if previous is not None:
                        previous.tail += img.tail
                    else:
                        parent.text = (parent.text or '') + img.tail

                img.drop_tree()

        except Exception as e:
            log.warning(f"Failed to process image node: {e}", exc_info=False)
            if img is not None and img.getparent() is not None:
                img.drop_tree()

GENERIC_WP_NOISE_XPATHS = [
    "//figcaption",
    "//div[@id='ez-toc-container']",
    "//div[contains(@class,'kk-star-ratings')]",
    "//div[contains(@class,'video')]",
    "//div[@class='feedback-container']",
    "//style",
    "//svg",
    "//script",
    "//footer",
    "//aside",
    "//button",
    "//*[contains(@class,'table-of-content')]",
    "//*[contains(@class,'embed')]",
    "//*[contains(@class,'Embed')]",
    "//p[.//strong/following::a]",
    "//p[contains(text(),'RELATED:')]",
    "//p[contains(text(),'related:')]",
    "//p[contains(text(),'For more information about')]",
    "//strong[contains(text(),'Related')]",
    "//*[contains(@class,'LinkSuggestion')]",
    "//div[@class='tasty-recipes-rating']",
    "//div[@class='tasty-recipes-details']",
    "//div[@class='tasty-recipes-buttons']",
    "//div[@class='tasty-recipes-cook-mode']",
    "//a[@class='button tasty-recipes-print-button tasty-recipes-no-print tasty-recipes-print-above-card']",
    "//span[@id='tasty-recipes-34969-jump-target']",
    "//div[contains(@class,'references')]",
    "//*[contains(text(),'click to')]",
    "//*[contains(text(), 'download')]",
    "//*[contains(text(), 'comment')]",
    "//*[contains(text(), 'visit')]",
    "//*[contains(text(),'related')]",
    "//*[contains(@class,'toc')]",
    "//div[@class='yarpp-thumbnails-horizontal']",
    "//ul[@class='amz']",
    "//*[contains(@class,'ads-')]",
    "//*[contains(@class,'advert')]",
    "//div[contains(@class,'related')]",
    "//details[@id='feast-advanced-jump-to']",
    "//ul[@class='feast-jump-to-list']",
    "//*[contains(@text,'Amazon')]",
    "//*[contains(@text,'amazon')]",
    "//div[contains(@class,'dpsp')]",
    "//p//em",
    "//strong[em]/em",
    "//strong[following-sibling::*[1][self::a]]",
    "//div[contains(@class,'slideshow')]",
    "//*[contains(@class,'cta')]",
    "//*[contains(@class,'call-to-action')]",
    "//div[contains(@class,'toggle')]",
    "//div[contains(@class,'switch')]",
    "//a[contains(@rel,'sponsor')]",
    "//div[@class='block-area block-area-before-recipe']",
    "//div[contains(@id,'rating')]",
    "//*[contains(@class,'btn-')]",
    "//*[contains(@class,'button')]",
    "//*[contains(@class,'-btn')]",
    "//div[@class='wp-block-group is-layout-constrained wp-block-group-is-layout-constrained']",
    "//*[contains(@class,'author')]",
    "//div[contains(@id,'dpsp')]",
    "//a[@rel='nofollow']"
]


def clean_html_body(html_content: str, args: argparse.Namespace) -> str:
    """
    Clean and normalize HTML content while retaining formatting such as newlines,
    ordered lists (1., 2., 3.), and single line spacing.
    """
    if not html_content or not html_content.strip():
        return ""

    try:
        parser = lxml_html.HTMLParser(recover=True, remove_comments=True)
        tree = lxml_html.fromstring(html_content, parser=parser)
    except (ParserError, ValueError, TypeError) as e:
        log.warning(f"LXML failed to parse content, returning empty. Error: {e}")
        return ""

    # 1. Prune unwanted XPaths
    if args.prune_xpath or not args.disable_default_prune:
        prunes = []
        if not args.disable_default_prune:
            prunes.extend(GENERIC_WP_NOISE_XPATHS)
        if args.prune_xpath:
            prunes.extend(args.prune_xpath)

        for xpath in prunes:
            try:
                for elem in tree.xpath(xpath):
                    parent = elem.getparent()
                    if parent is not None:
                        elem.drop_tree()
            except Exception as e:
                log.warning(f"Error processing prune_xpath '{xpath}': {e}")

    # 2. Remove outro
    if args.remove_outro:
        try:
            last_element = tree.xpath('(//p|//em)[last()]')
            if last_element:
                element_to_remove = last_element[0]
                parent = element_to_remove.getparent()
                if parent is not None and len(parent) > 1:
                    element_to_remove.drop_tree()
        except Exception as e:
            log.warning(f"Error during remove_outro: {e}")

    # 3. Convert Tables and Images
    _convert_tables_to_latex(tree)
    _convert_images_to_text(tree)

    # 4. Handle links - preserve href but remove anchor tags
    # This fixes the issue where anchor text runs together with surrounding text
    for a in tree.xpath('//a'):
        # Add space before and after link text to prevent text concatenation
        if a.text:
            a.text = f" {a.text.strip()} "
        # If the link has a tail, ensure proper spacing
        if a.tail:
            a.tail = f" {a.tail.lstrip()}"
        else:
            a.tail = " "

    # 5. Convert <br> tags to newlines
    for br in tree.xpath('//br'):
        # Ensure br.tail exists before concatenating
        br.tail = '\n' + (br.tail or '')

    # 6. Handle paragraphs with single newline spacing
    for p in tree.xpath('//p'):
        # Clean up paragraph text
        if p.text:
            p.text = p.text.strip()

        # Single newline after paragraphs
        if p.tail is None:
            p.tail = '\n'
        elif not p.tail.strip():
            p.tail = '\n'
        else:
            p.tail = f"\n{p.tail.lstrip()}"

    # 7. Handle ordered lists with proper numbering
    for ol in tree.xpath('//ol'):
        # Handle start attribute if present
        start_num = 1
        try:
            start_attr = ol.get('start')
            if start_attr:
                start_num = int(start_attr)
        except (ValueError, TypeError):
            start_num = 1

        for i, li in enumerate(ol.xpath('./li'), start_num):
            prefix = f"{i}. "
            if li.text:
                li.text = prefix + li.text.strip()
            else:
                li.text = prefix

            # Single newline after list item
            if li.tail is None:
                li.tail = '\n'
            else:
                li.tail = '\n' + li.tail.lstrip()

    # 8. Handle unordered lists
    for ul in tree.xpath('//ul'):
        for li in ul.xpath('./li'):
            text = (li.text or '').strip()
            li.text = f"- {text}" if text else "-"

            # Single newline after list item
            if li.tail is None:
                li.tail = '\n'
            else:
                li.tail = '\n' + li.tail.lstrip()

    # 9. Extract text
    try:
        text = tree.text_content()
    except Exception as e:
        log.warning(f"LXML text_content() failed: {e}")
        text = ""

    if not text:
        return ""

    # 10. Discard Emojis
    if args.discard_emoji:
        text = EMOJI_REGEX.sub('', text)

    # 11. Anonymize
    if args.anonymize:
        repl_func = lambda m: 'x' * len(m.group(0))
        text = EMAIL_REGEX.sub(repl_func, text)
        text = PHONE_REGEX.sub(repl_func, text)
        text = SOCIAL_REGEX.sub(repl_func, text)

    # 12. Normalize spacing - maximum 1 consecutive newline
    # First, normalize spaces and tabs (but not newlines)
    text = re.sub(r'[ \t]+', ' ', text)

    # Remove spaces at the beginning/end of lines
    text = re.sub(r' *\n *', '\n', text)

    # Collapse ALL multiple newlines to single newline (2+ newlines -> 1 newline)
    text = re.sub(r'\n+', '\n', text)

    # Replace box drawing characters with hyphens
    text = re.sub(r'[▢□■▪▫]', '-', text)

    # Handle common HTML entities that might slip through
    text = re.sub(r'&nbsp;', ' ', text)
    text = re.sub(r'&[a-z]+;', ' ', text)  # Replace other entities with space

    # Final cleanup: normalize multiple spaces that may have been created
    text = re.sub(r' {2,}', ' ', text)

    return text.strip()

# === Main Worker ===

IGNORE_CATEGORY_LIST = [
    "uncategorized"
]


@staticmethod
def parse_domain_subdomain_args(body: dict, domain: Optional[str], subdomain: Optional[str]) -> tuple[str, str]:
    args_dom = domain.split("??")
    args_sub = subdomain.split("??")

    # Extract main value and fallback for domain
    if len(args_dom) < 2:
        domain_value = args_dom[0]
        domain_fallback = None
    else:
        domain_value = args_dom[0]
        domain_fallback = args_dom[1]

    # Extract main value and fallback for subdomain
    if len(args_sub) < 2:
        subdomain_value = args_sub[0]
        subdomain_fallback = None
    else:
        subdomain_value = args_sub[0]
        subdomain_fallback = args_sub[1]

    class_list = body.get('class_list')

    if not isinstance(class_list, list):
        if isinstance(class_list, dict):
            class_list = list(class_list.values())
        else:
            class_list = None

    # Try to infer domain from class_list
    domain_found = False
    if class_list and "@" in domain_value:
        if domain_value.replace("@", "").lower().strip() == "class_list":
            for c in class_list:
                if "category-" in c.lower().strip():
                    parsed_domain = c.replace("category-", "").strip()
                    if parsed_domain not in IGNORE_CATEGORY_LIST:
                        domain = parsed_domain
                        domain_found = True
                        break

            # Use fallback if inference failed
            if not domain_found and domain_fallback:
                domain = domain_fallback
    else:
        domain = domain_value

    # Try to infer subdomain from class_list
    subdomain_found = False
    if class_list and "@" in subdomain_value:
        if subdomain_value.replace("@", "").lower().strip() == "class_list":
            for c in class_list:
                if "category-" in c.lower().strip():
                    s = c.replace("category-", "").strip()
                    if s.lower() != domain.lower():
                        parsed_subdomain = s
                        if parsed_subdomain not in IGNORE_CATEGORY_LIST:
                            subdomain = parsed_subdomain
                            subdomain_found = True
                            break

            # Use fallback if inference failed
            if not subdomain_found and subdomain_fallback:
                subdomain = subdomain_fallback
    else:
        subdomain = subdomain_value

    return domain, subdomain



def process_line(line: str, args: argparse.Namespace, seen_urls_proxy: Dict) -> Optional[str]:
    """
    Processes a single line from the JSONL file.
    This is the target function for each parallel worker.
    """
    try:
        line_data = json.loads(line)
        # 1. Get URL for deduplication
        url = line_data.get('url')
        # 2. Deduplication check
        if not args.disable_dedupe and url:
            if url in seen_urls_proxy:
                # Log this info-level, not as a warning
                # log.info(f"Skipping duplicate URL: {url}")
                return "DUPLICATE"  # Return a specific marker
            seen_urls_proxy[url] = 1  # Add to shared dict
        # 3. Load the stringified 'body'
        try:
            body_obj = json.loads(line_data.get('body', '{}'))
        except (json.JSONDecodeError, TypeError):
            log.warning(f"Could not decode 'body' field. Skipping line with id {line_data.get('id')}")
            return "ERROR"

        # 4. Extract and Clean Title
        raw_title = body_obj.get('title', {}).get('rendered', '')
        if args.clean_title:
            cleaned_title = clean_title_func(raw_title, args.clean_title_template, args.clean_title_html)
            if args.clean_title_emoji:
                cleaned_title = EMOJI_REGEX.sub('', cleaned_title)
        else:
            cleaned_title = raw_title.strip()

        # 5. Extract and Clean Body
        raw_body = body_obj.get('content', {}).get('rendered', '')

        # --- NEW: Check min-body-process ---
        if len(raw_body) < args.min_body_process:
            # log.info(f"Skipping line {line_data.get('id')}: raw body length ({len(raw_body)}) < min-body-process ({args.min_body_process})")
            return "SKIPPED_BODY"

        if args.clean_body:
            cleaned_body = clean_html_body(raw_body, args)
        else:
            cleaned_body = re.sub(r'\s+', ' ', lxml_html.fromstring(raw_body).text_content()).strip()

        if args.append_featured_media:
            intro_img = body_obj.get('jetpack_featured_media_url')
            if intro_img:
                cleaned_body = f"[Image: {intro_img}\\]\n\n{cleaned_body}"

        # 6. Combine text
        text = f"{cleaned_title}\n{cleaned_body}"

        if len(text) < args.min_text_length:
            # log.info(f"Skipping line {line_data.get('id')}: final text length ({len(text)}) < min-text-length ({args.min_text_length})")
            return "SKIPPED_TEXT"

        # 7. Prepare Output
        output_id = line_data.get('id') or str(uuid.uuid4())
        input_meta = line_data.get('meta', {})

        domain,subdomain = parse_domain_subdomain_args(body_obj,args.domain,args.subdomain)

        output_data = {
            "id": output_id,
            "text": text,
            "meta": {
                "data_info": {
                    "lang": "en",
                    "url": url,
                    "source": input_meta.get('site'),
                    "type": args.type or "website_content",
                    "processing_date": datetime.now().isoformat(),
                    "delivery_version": args.version or "v1",
                    "title": cleaned_title
                },
                "content_info": {
                    "domain": domain or "daily life",
                    "subdomain": subdomain or "practical tips & guides"
                }
            }
        }

        # --- MODIFIED: Return as a JSON string with ensure_ascii=False ---
        return json.dumps(output_data, ensure_ascii=False)

    except Exception as e:
        log.error(f"Failed to process line: {e}. Line (truncated): {line[:200]}...")
        return "ERROR"


def reader_process(filepath: str, input_queue: Queue, limit: Optional[int]):
    """Reads lines from the file and puts them into the input queue."""
    log.info(f"[Reader] Starting to read file: {os.path.basename(filepath)}")
    lines_read = 0
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                if limit and lines_read >= limit:
                    break

                # Non-blocking, almost always immediate
                input_queue.put(line)
                lines_read += 1

    except Exception as e:
        log.error(f"[Reader] Critical error during file read: {e}", exc_info=True)

    finally:
        # Signal workers that no more data is coming
        for _ in range(os.cpu_count()):  # Put N 'None' markers for N workers
            input_queue.put(None)
        log.info(f"[Reader] Finished reading {lines_read} lines. Shutting down.")


def worker_process(input_queue: Queue, output_queue: Queue, args: argparse.Namespace, seen_urls_proxy: Dict):
    """Pulls lines from input queue, processes them, and puts results into output queue."""

    worker_id = os.getpid()
    while True:
        try:
            # Short timeout to allow for clean shutdown if queues are empty
            line = input_queue.get(timeout=0.1)
        except Empty:
            continue

        if line is None:
            # Sentinel value received, stop processing
            break

        result = process_line(line, args, seen_urls_proxy)

        # Put result into the output queue (can be a JSON string or a SKIPPED/ERROR marker)
        output_queue.put(result)

    # Put a None sentinel into the output queue to signal the writer
    output_queue.put(None)
    log.debug(f"[Worker {worker_id}] Shutting down.")


def writer_process(output_queue: Queue, output_file: str, file_limit: Optional[int]):
    """Pulls processed results from the output queue and writes them to the file."""

    log.info(f"[Writer] Starting to write to {os.path.basename(output_file)}")
    sentinels_received = 0
    workers_to_wait_for = os.cpu_count()
    records_written = 0
    records_skipped = 0

    pbar = tqdm(total=file_limit, desc=f"Cleaning & Writing {os.path.basename(output_file)}",
                unit="lines", dynamic_ncols=True)

    start_time = time.time()

    try:
        with open(output_file, 'w', encoding='utf-8') as f_out:
            while sentinels_received < workers_to_wait_for:
                try:
                    # Longer timeout is acceptable here
                    result = output_queue.get(timeout=0.5)
                except Empty:
                    # Display the current rate even if the queue is temporarily empty
                    pbar.refresh()
                    continue

                if result is None:
                    # This is a worker sentinel, count it
                    sentinels_received += 1
                elif result and not result.startswith("SKIPPED_") and not result.startswith(
                        "DUPLICATE") and not result.startswith("ERROR"):
                    # This is a good JSON line
                    f_out.write(result + '\n')
                    records_written += 1
                else:
                    # This is a skipped/error marker
                    records_skipped += 1

                # Update progress bar for every item consumed
                if result is not None:
                    pbar.update(1)

    except Exception as e:
        log.error(f"[Writer] Critical error during file write: {e}", exc_info=True)

    finally:
        end_time = time.time()
        elapsed = end_time - start_time
        log.info(f"[Writer] Finished. Wrote {records_written} records (Skipped {records_skipped}). "
                 f"Total elapsed: {elapsed:.2f}s. Rate: {records_written / elapsed:.2f} lines/sec.")
        pbar.close()
        return records_written, records_skipped

# === Main Execution ===

def main():
    # ... (Parser setup remains unchanged) ...
    parser = argparse.ArgumentParser(description="Parallel WordPress JSONL Data Cleaner")

    # --- Input ---
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--input-file', type=str, help="Path to a single input JSONL file.")
    group.add_argument('--input-dir', type=str, help="Path to a directory containing .jsonl files.")

    # --- Output ---
    parser.add_argument('--output', type=str, help="Output file name. (Default: {filename}_cleaned_{version}.jsonl)")
    parser.add_argument('--version', type=str, default='v1', help="Delivery version for output meta and filename.")

    # --- Cleaning ---
    parser.add_argument('--clean-title', action='store_true', default=True,
                        help="Enable title cleaning (strip, unescape). Default: True")

    parser.add_argument('--no-clean-title', dest='clean_title', action='store_false', help="Disable title cleaning.")

    parser.add_argument("--clean-title-html", action="store_true", default=False,
                        help="Enable title cleaning (HTML). Default: false")

    parser.add_argument('--clean-title-template', action='store_true', default=True,
                        help="Remove ' | Site' or ' - Site' templates from title. Default: True")
    parser.add_argument('--no-clean-title-template', dest='clean_title_template', action='store_false',
                        help="Disable title template removal.")

    parser.add_argument('--clean-body', action='store_true', default=True,
                        help="Enable body cleaning (HTML, whitespace). Default: True")
    parser.add_argument('--no-clean-body', dest='clean_body', action='store_false', help="Disable body cleaning.")

    parser.add_argument('--anonymize', action='store_true', default=False,
                        help="Anonymize emails, phone numbers, and social media links. Replaced with 'x'.")

    parser.add_argument('--discard-emoji', action='store_true', default=False, help="Remove all emoji characters.")

    parser.add_argument('--prune-xpath', nargs='*', default=[],
                        help="List of XPath expressions to prune from the HTML tree.")

    parser.add_argument('--remove-outro', action='store_true', default=False,
                        help="Attempt to remove the last <p> or <em> tag (e.g., CTA).")

    parser.add_argument('--clean-title-emoji', action='store_true', default=False,)

    parser.add_argument("--disable-default-prune", action="store_true", default=False,
                        help="Disable the default pruning rules (see --prune-xpath).")

    # --- Filtering ---
    parser.add_argument('--min-text-length', type=int, default=200,
                        help="Drop final text shorter than this. (Default: 200)")

    parser.add_argument('--min-body-process', type=int, default=220,
                        help="Do not process 'body' field if raw char length is less than this. (Default: 220)")

    # --- Processing ---
    parser.add_argument('-w', '--workers', type=int, default=os.cpu_count(),
                        help=f"Number of parallel workers. (Default: All available cores = {os.cpu_count()})")

    parser.add_argument('--chunksize', type=int, default=100,  # Chunksize is now irrelevant, but kept for compatibility
                        help="Number of lines to send to each worker at a time. (Default: 100)")

    parser.add_argument('--disable-dedupe', action='store_true', default=False,
                        help="Disable URL-based deduplication. (Default: Deduplication is ON)")

    parser.add_argument('--append-featured-media', action='store_true', default=False)

    parser.add_argument('--limit', type=int, default=None, help="Limit processing to the first N records per file.")

    # --- Metadata ---
    parser.add_argument('--domain', type=str, default='unclassified', help="Value for output.meta.content_info.domain")

    parser.add_argument('--subdomain', type=str, default='unclassified',
                        help="Value for output.meta.content_info.subdomain")

    parser.add_argument('--type', type=str, default='website_content', help="Value for output.meta.data_info.type")

    args = parser.parse_args()

    # ... (Input file finding logic remains unchanged) ...
    input_files: List[str] = []
    if args.input_file:
        if os.path.exists(args.input_file):
            input_files.append(args.input_file)
        else:
            log.error(f"Input file not found: {args.input_file}")
            sys.exit(1)
    elif args.input_dir:
        if os.path.isdir(args.input_dir):
            for f in os.listdir(args.input_dir):
                if f.endswith('.jsonl'):
                    input_files.append(os.path.join(args.input_dir, f))
        else:
            log.error(f"Input directory not found: {args.input_dir}")
            sys.exit(1)

    if not input_files:
        log.error("No .jsonl input files found.")
        sys.exit(1)
    # ... (End of input file finding logic) ...

    log.info(f"Starting pipeline with {args.workers} worker processes and 1 dedicated Reader/Writer.")

    # --- Setup Shared State for Deduplication ---
    # This remains the single potential bottleneck, but it's unavoidable if deduplication is required.
    manager = Manager()
    seen_urls_proxy = manager.dict()

    total_processed = 0
    total_skipped = 0

    # --- Process Each File ---
    for filepath in input_files:
        log.info(f"--- Processing file: {filepath} ---")

        # 1. Determine output filename
        if args.output and len(input_files) == 1:
            output_file = args.output
        else:
            base_name = os.path.basename(filepath)
            filename, _ = os.path.splitext(base_name)
            output_file = os.path.join(os.path.dirname(filepath), f"{filename}_cleaned_{args.version}.jsonl")

        log.info(f"Output will be written to: {output_file}")

        # 2. Setup Queues
        input_queue = Queue()
        output_queue = Queue()

        # 3. Setup Processes

        # Reader: Reads file lines into input_queue
        reader = Process(target=reader_process, args=(filepath, input_queue, args.limit))

        # Workers: Read from input_queue, process, write to output_queue
        workers = []
        for i in range(args.workers):
            p = Process(target=worker_process, args=(input_queue, output_queue, args, seen_urls_proxy))
            workers.append(p)

        # Writer: Reads results from output_queue and writes to file
        writer = Process(target=writer_process, args=(output_queue, output_file, args.limit))

        # 4. Start Pipeline

        reader.start()
        for p in workers:
            p.start()
        writer.start()

        # 5. Wait for Reader and Workers to finish

        reader.join()
        for p in workers:
            p.join()

        # 6. Wait for Writer to finish (it will finish once all workers are done)
        writer.join()

        # 7. Collect Results (Note: We'd need to modify writer to return stats via a Pipe/Value
        #    or just rely on the log output for simplicity.)
        # For simplicity and to avoid complexity, we rely on the writer's log output now.
        # total_processed += writer_result[0]
        # total_skipped += writer_result[1]

    log.info("--- 💥 GO BRR Complete! ---")
    log.info("Check the log output for final counts and lines/sec.")


if __name__ == "__main__":
    main()

