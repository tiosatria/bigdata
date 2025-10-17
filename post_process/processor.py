#!/usr/bin/env python3
"""
Processor: converts raw crawl records (JSON/JSONL) into standardized JSONL records.
- Output schema:
  {
    'id': <uuid4>,
    'text': f"{title}\n{body}",
    'meta': {
      'data_info': {
        'lang': <lang>, 'url': <url>, 'source': <source_domain>, 'type': 'general',
        'processing_date': <timestamp>, 'delivery_version': 'V1', 'title': <title>
      },
      'content_info': {'domain': <source_type>, 'subdomain': <subcat>}
    }
  }
- Uses JSONLoader for streamed reading with progress.
- Parallel chunk processing with ProcessPoolExecutor and tqdm progress.
"""
import argparse
import json
import sys
import uuid
from pathlib import Path
from multiprocessing import cpu_count
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import List, Dict, Any, Optional
from tqdm import tqdm

from post_process.jsonloader import JSONLoader

# Optional: domain config loading (used to select cleaning pipeline in the future)
try:
    from bigdata.domain_configs import DomainConfigRegistry
except Exception:
    DomainConfigRegistry = None  # Fallback if registry not available


# ---------------
# Worker functions
# ---------------

def _convert_record(record: Dict[str, Any], min_text_length: int, fallback_domain: str,
                    fallback_subdomain: Optional[str]) -> (Optional[Dict[str, Any]], Optional[Dict[str, Any]]):
    """Convert a single raw record to the target schema.
    Returns (ok_record, fail_record). Only one of them is non-None.
    """
    if not isinstance(record, dict):
        return None, {
            'reason': 'invalid_record',
            'details': 'not a dict'
        }

    title = (record.get('title') or '').strip()
    body = record.get('body') or ''

    if not title and not body:
        # Save minimal info for failed file
        return None, {
            'reason': 'empty_content',
            'url': record.get('url'),
            'title': title,
            'source_domain': record.get('source_domain'),
            'lang': record.get('lang'),
            'text_length': 0
        }

    # Defaults for missing fields
    lang = (record.get('lang') or None)
    url = (record.get('url') or '').strip()
    source_domain = record.get('source_domain') or None

    from datetime import datetime, timezone
    timestamp = record.get('timestamp') or record.get('post_date')
    if not timestamp:
        timestamp = datetime.now(timezone.utc).isoformat()

    # Infer domain/subdomain from tags if possible
    tags = record.get('tags')
    tag_list: List[str] = []
    if isinstance(tags, list):
        tag_list = [str(t) for t in tags if t is not None]
    elif isinstance(tags, str):
        tag_list = [tags]
    # Clean tags
    tag_list_clean = [t.strip() for t in tag_list if str(t).strip()]

    # helper to skip 'home'
    def is_home(val: str) -> bool:
        return str(val).strip().lower() == 'home'

    domain_tag = None
    for t in tag_list_clean:
        if not is_home(t):
            domain_tag = t
            break
    subdomain_tag = None
    for t in reversed(tag_list_clean):
        if not is_home(t):
            subdomain_tag = t
            break
    if subdomain_tag and domain_tag and subdomain_tag == domain_tag:
        subdomain_tag = None

    domain_val = domain_tag or fallback_domain or 'general'
    subdomain_val = subdomain_tag or (fallback_subdomain or '')

    text = f"{title}\n{body}".strip()
    if len(text) < int(min_text_length):
        return None, {
            'reason': 'too_short',
            'url': url,
            'title': title,
            'source_domain': source_domain,
            'lang': lang,
            'text_length': len(text)
        }

    out = {
        'id': str(uuid.uuid4()),
        'text': text,
        'meta': {
            'data_info': {
                'lang': lang,
                'url': url,
                'source': source_domain,
                'type': subdomain_val,
                'processing_date': timestamp,
                'delivery_version': 'V1',
                'title': title
            },
            'content_info': {
                'domain': domain_val,
                'subdomain': subdomain_val
            }
        }
    }
    return out, None


def _process_chunk(chunk: List[Dict[str, Any]], min_text_length: int, fallback_domain: str,
                   fallback_subdomain: Optional[str], source_name: Optional[str] = None) -> Dict[
    str, List[Dict[str, Any]]]:
    """Process a list of records to the output schema.
    Returns dict with keys 'ok' and 'fail'.
    If source_name is provided, try to load and apply cleaning pipeline.
    """
    ok: List[Dict[str, Any]] = []
    fail: List[Dict[str, Any]] = []

    # Try to load pipeline in worker process (avoid serialization overhead)
    pipeline = None
    if source_name and DomainConfigRegistry is not None:
        try:
            DomainConfigRegistry.load_all_configs()
            cfg = DomainConfigRegistry.get(source_name)
            if cfg:
                pipeline = getattr(cfg, 'cleaning_pipelines', None)
        except Exception:
            pass

    for rec in chunk:
        try:
            item = rec
            if pipeline is not None:
                # Defensive: ensure required keys exist
                if 'title' not in item:
                    item['title'] = ''
                if 'body' not in item:
                    item['body'] = ''
                if 'tags' not in item:
                    item['tags'] = []
                item = pipeline.process_item(item)
        except Exception:
            # If cleaning fails, fall back to original
            item = rec
        converted, failed = _convert_record(item, min_text_length, fallback_domain, fallback_subdomain)
        if converted is not None:
            ok.append(converted)
        elif failed is not None:
            fail.append(failed)
    return {'ok': ok, 'fail': fail}


# ---------------
# Main CLI
# ---------------

def _infer_source_from_filename(input_path: Path) -> str:
    stem = input_path.stem
    # common convention: example_com.jsonl -> example.com
    return stem.replace('_', '.')


def main():
    parser = argparse.ArgumentParser(description='Export data to JSONL format with parallel processing.')
    parser.add_argument('--input', '-i', required=True, help='Input file must be JSON or JSONL')
    parser.add_argument('--output', type=str, help='Output JSONL file path')
    parser.add_argument('--source', type=str, help='source domain to clean. '
                                                   'if you do not fill this, the file name will then be used to determine which domain it comes from. file name convention sample: example_com.jsonl')
    parser.add_argument('--workers', type=int, default=cpu_count(),
                        help=f'Number of parallel worker processes to use (default: {cpu_count()})')
    parser.add_argument('--limit', type=int, help='Limit the number of records to process')
    parser.add_argument('--chunk-size', type=int, default=1000,
                        help='Records per chunk for parallel processing (default: 1000)')
    parser.add_argument('--min-text-length', type=int, default=200,
                        help='Minimum length of combined title+body text to keep (default: 200)')

    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = input_path.with_name(f"{input_path.stem}_processed.jsonl")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Infer source/domain name
    source_name = args.source.strip() if args.source else _infer_source_from_filename(input_path)

    # Load domain configs (optional) and infer domain config if possible
    cfg = None
    if DomainConfigRegistry is not None:
        try:
            DomainConfigRegistry.load_all_configs()
            cfg = DomainConfigRegistry.get(source_name)
            if cfg is None and '.' not in source_name:
                # Try appending .com if not present (best-effort)
                cfg = DomainConfigRegistry.get(source_name + '.com')
            if cfg is None:
                # Fuzzy match: find first domain containing the filename signature
                all_domains = DomainConfigRegistry.get_all_domains()
                key = source_name.lower()
                for dom in all_domains:
                    dl = dom.lower()
                    if key in dl or dl in key or dl.startswith(key) or key.startswith(dl):
                        cfg = DomainConfigRegistry.get(dom)
                        break
            if cfg is None:
                msg = (f"Could not infer domain config from filename '{input_path.name}'. "
                       f"Please provide --source explicitly.")
                print(msg, file=sys.stderr)
                if not args.source:
                    sys.exit(1)
            else:
                print(f"Using domain config for: {cfg.domain}")
        except Exception as e:
            print(f"Warning: failed to initialize DomainConfigRegistry: {e}", file=sys.stderr)
            cfg = None

    # Initialize JSON loader WITHOUT nested progress bar
    loader = JSONLoader(path=input_path, chunk_size=max(1, args.chunk_size), desc=None)
    try:
        total_count = loader.count()
    except Exception:
        total_count = None

    limit = args.limit if args.limit is not None else total_count
    total_to_process = min(total_count, limit) if (
                total_count is not None and limit is not None) else limit or total_count

    # Parallel processing
    max_workers = max(1, args.workers or cpu_count())

    print(f"Input: {input_path}")
    print(f"Output: {output_path}")
    print(f"Source domain: {source_name}")
    print(f"Workers: {max_workers}")
    if total_to_process is not None:
        print(f"Planned to process: {total_to_process:,} records")
    print("-" * 50)

    failed_path = input_path.with_name(f"{input_path.stem}_failed.jsonl")

    # Determine fallbacks from domain config
    fallback_domain = getattr(cfg, 'domain_type', 'general') if cfg else 'general'
    fallback_subdomain = getattr(cfg, 'subdomain', None) if cfg else None

    # Collect all chunks first for better progress tracking
    print("Loading data...")
    all_chunks = list(loader.iter_chunks(limit=limit))
    total_records = sum(len(chunk) for chunk in all_chunks)
    print(f"Loaded {len(all_chunks):,} chunks ({total_records:,} records)")

    written = 0
    failed_count = 0

    with output_path.open('w', encoding='utf-8') as fout:
        ffail = None
        with ProcessPoolExecutor(max_workers=max_workers) as executor:
            # Submit all work at once (much faster than incremental submission)
            futures = {
                executor.submit(_process_chunk, chunk, int(args.min_text_length),
                                fallback_domain, fallback_subdomain, source_name): len(chunk)
                for chunk in all_chunks
            }

            try:
                # Single progress bar tracking records processed
                with tqdm(total=total_records, desc="Processing", unit=" rec", dynamic_ncols=True) as pbar:
                    for future in as_completed(futures):
                        chunk_size = futures[future]
                        try:
                            results = future.result()
                            ok = results.get('ok', [])
                            fail = results.get('fail', [])

                            # Write results
                            for rec in ok:
                                fout.write(json.dumps(rec, ensure_ascii=False) + "\n")
                                written += 1

                            for fr in fail:
                                if ffail is None:
                                    ffail = failed_path.open('w', encoding='utf-8')
                                ffail.write(json.dumps(fr, ensure_ascii=False) + "\n")
                                failed_count += 1

                            # Update progress
                            pbar.update(len(ok) + len(fail))
                        except Exception as e:
                            print(f"\nError processing chunk: {e}", file=sys.stderr)
                            pbar.update(chunk_size)

            except KeyboardInterrupt:
                print("\nInterrupted by user, shutting down...", file=sys.stderr)
                executor.shutdown(wait=False, cancel_futures=True)
                raise

        # Close failed file if opened
        if ffail is not None:
            try:
                ffail.close()
            except Exception:
                pass

    # Print final summary
    if failed_count:
        print(
            f"\n✓ Finished. Wrote {written:,} records to {output_path}. Failed/filtered: {failed_count:,} -> {failed_path}")
    else:
        try:
            if failed_path.exists():
                failed_path.unlink()
        except Exception:
            pass
        print(f"\n✓ Finished. Wrote {written:,} records to {output_path}. Failed/filtered: 0")


if __name__ == '__main__':
    main()