#!/usr/bin/env python3
"""
classifier.py

Stream and classify JSONL records (infer domain & subdomain from url/title/text).
- Input JSONL line format (one JSON object per line):
  {
    "id": "<guid>",
    "meta": {
      "data_info": {"url": "...", "title": "...", "type": "..."},
      "content_info": {"domain": "...", "subdomain": "..."}
    },
    "text": "title\ncleaned_content"
  }

- Output: same JSONL but with meta.content_info.domain and meta.content_info.subdomain replaced
- Streaming, multiprocessing, separate reader/writer, no pre-counting lines
- Ctrl+C gracefully stops processing

Usage:
  python classifier.py [paths...] [--rewrite] [--rewrite-path PATH]
                       [--fallback-domain DOMAIN] [--fallback-subdomain SUB]
                       [--force-domain DOMAIN] [--force-subdomain SUB]
                       [--worker N]

If a path is a directory, all *.jsonl files inside are processed sequentially (one file at a time).
"""

import argparse
import json
import os
import re
import sys
import tempfile
import shutil
import signal
from multiprocessing import Process, Queue, cpu_count, Event
import threading
from tqdm import tqdm

# ---------------------------
# Keyword maps and heuristics
# ---------------------------

# Top-level domains and representative keywords
KEYWORD_MAP = {
    "home_care": [
        "home care", "homecare", "household", "housekeeping", "home cleaning", "cleaning",
        "laundry", "stain", "stain removal", "storage", "organize", "declutter", "storage solutions",
        "odor", "air fresh", "mold", "disinfect", "sanitize"
    ],
    "cooking_food": [
        "recipe", "cook", "cooking", "kitchen", "food", "preserve", "preservation", "canning",
        "ferment", "meal", "bake", "grill", "food safety", "nutrition", "food knowledge"
    ],
    "health_personal_care": [
        "health", "wellness", "remedy", "natural remedy", "home remedy", "skincare", "personal care",
        "first aid", "treatment", "allergy", "immune", "supplement"
    ],
    "diy_handcrafts": [
        "diy", "do it yourself", "craft", "handcraft", "upcycle", "repurpose", "repurposing",
        "woodworking", "sewing", "knit", "crochet", "repair", "how to make"
    ],
    "odor_home_env": [
        "odor", "smell", "air quality", "ventilation", "deodorize", "air purifier", "mildew", "mold",
        "freshen", "scent", "odor removal"
    ],
    "healthy_drinks_allergy": [
        "smoothie", "juice", "healthy drink", "allergy-safe", "dairy-free", "vegan", "substitute",
        "milk alternative", "almond milk", "soy milk", "lactose-free", "allergen"
    ],
}

# Subdomain keywords per domain (ordered heuristics)
SUBDOMAIN_MAP = {
    "home_care": {
        "stain_removal": ["stain", "stain removal", "remove stains", "laundry"],
        "cleaning_tips": ["clean", "cleaning", "housekeeping", "disinfect", "sanitize"],
        "storage_solutions": ["storage", "organize", "declutter", "shelf", "container"],
        "odor_removal": ["odor", "smell", "deodorize", "freshen"],
    },
    "cooking_food": {
        "recipes": ["recipe", "cook", "bake", "grill", "meal"],
        "food_preservation": ["preserve", "canning", "ferment", "preservation", "freeze"],
        "food_knowledge": ["nutrition", "food safety", "food knowledge", "ingredients"],
    },
    "health_personal_care": {
        "natural_remedies": ["remedy", "home remedy", "natural remedy", "herbal"],
        "common_treatments": ["treatment", "first aid", "care", "therapy"],
        "skincare": ["skin", "skincare", "acne", "moisturizer"],
    },
    "diy_handcrafts": {
        "crafts": ["craft", "handcraft", "sewing", "knit", "crochet"],
        "repurposing": ["repurpose", "upcycle", "reuse", "repurposing"],
        "howto": ["how to", "tutorial", "guide", "instructions"],
    },
    "odor_home_env": {
        "air_quality": ["air quality", "ventilation", "purifier", "filter"],
        "odor_removal": ["odor", "deodorize", "smell", "freshen"],
        "mold_mildew": ["mold", "mildew", "damp"],
    },
    "healthy_drinks_allergy": {
        "smoothies": ["smoothie", "juice", "blend"],
        "allergy_substitutes": ["allergy", "substitute", "dairy-free", "milk alternative", "vegan"],
        "nutritional_drinks": ["protein", "shake", "nutrient", "vitamin"],
    },
}

# Fallback domain/subdomain names when nothing matches
DEFAULT_DOMAIN = "unknown"
DEFAULT_SUBDOMAIN = "general"

# ---------------------------
# Utility functions
# ---------------------------

TOKEN_RE = re.compile(r"[A-Za-z0-9]+")

def tokenize(text):
    if not text:
        return []
    return TOKEN_RE.findall(text.lower())

def host_from_url(url):
    try:
        # crude extraction
        m = re.search(r"^(?:https?://)?([^/]+)", url or "")
        host = m.group(1).lower() if m else ""
        # strip port
        host = host.split(":")[0]
        return host
    except Exception:
        return ""

def score_for_keywords(tokens, keywords):
    # tokens: list of tokens; keywords: list of phrases
    score = 0
    text = " ".join(tokens)
    for kw in keywords:
        kw = kw.lower()
        if " " in kw:
            if kw in text:
                score += 3
        else:
            # single token
            score += tokens.count(kw)
    return score

def infer_domain_subdomain(url, title, text, fallback_domain=None, fallback_subdomain=None):
    """
    Heuristic scoring across url host, title, and text to pick domain and subdomain.
    Returns (domain, subdomain)
    """
    host = host_from_url(url)
    tokens = tokenize(" ".join([host, title or "", text or ""]))

    # domain scoring
    best_domain = None
    best_score = 0
    for domain, kws in KEYWORD_MAP.items():
        s = score_for_keywords(tokens, kws)
        # boost if host contains domain-like token
        if domain.replace("_", "") in host:
            s += 2
        if s > best_score:
            best_score = s
            best_domain = domain

    if best_score == 0:
        domain = fallback_domain if fallback_domain is not None else DEFAULT_DOMAIN
    else:
        domain = best_domain

    # subdomain scoring
    subdomain = DEFAULT_SUBDOMAIN
    if domain in SUBDOMAIN_MAP:
        best_sub = None
        best_sub_score = 0
        for sub, kws in SUBDOMAIN_MAP[domain].items():
            s = score_for_keywords(tokens, kws)
            if s > best_sub_score:
                best_sub_score = s
                best_sub = sub
        if best_sub_score == 0:
            subdomain = fallback_subdomain if fallback_subdomain is not None else DEFAULT_SUBDOMAIN
        else:
            subdomain = best_sub
    else:
        subdomain = fallback_subdomain if fallback_subdomain is not None else DEFAULT_SUBDOMAIN

    return domain, subdomain

# ---------------------------
# Worker, reader, writer
# ---------------------------

SENTINEL = None

def worker_main(in_q: Queue, out_q: Queue, stop_event: Event,
                force_domain, force_subdomain, fallback_domain_arg, fallback_subdomain_arg):
    """
    Worker process: consumes raw JSON lines, infers domain/subdomain, and emits updated JSON lines.
    """
    while True:
        try:
            item = in_q.get()
        except Exception:
            break
        if item is SENTINEL:
            # propagate sentinel to writer
            out_q.put(SENTINEL)
            break
        if stop_event.is_set():
            # graceful exit
            out_q.put(SENTINEL)
            break

        line = item
        try:
            obj = json.loads(line)
        except Exception:
            # malformed JSON: skip but keep original line
            out_q.put(line.rstrip("\n"))
            continue

        # read existing fallback from record if requested
        record_fallback_domain = None
        record_fallback_subdomain = None
        try:
            record_fallback_domain = obj.get("meta", {}).get("content_info", {}).get("domain")
            record_fallback_subdomain = obj.get("meta", {}).get("content_info", {}).get("subdomain")
        except Exception:
            pass

        # determine effective fallback values
        effective_fallback_domain = fallback_domain_arg if fallback_domain_arg is not None else record_fallback_domain
        effective_fallback_subdomain = fallback_subdomain_arg if fallback_subdomain_arg is not None else record_fallback_subdomain

        # if force flags present, use them directly
        if force_domain is not None:
            domain = force_domain
        else:
            url = obj.get("meta", {}).get("data_info", {}).get("url", "")
            title = obj.get("meta", {}).get("data_info", {}).get("title", "")
            text = obj.get("text", "")
            domain, _ = infer_domain_subdomain(url, title, text,
                                              fallback_domain=effective_fallback_domain,
                                              fallback_subdomain=effective_fallback_subdomain)

        if force_subdomain is not None:
            subdomain = force_subdomain
        else:
            # run inference again to get subdomain (infer_domain_subdomain returns both)
            if force_domain is not None:
                # if domain forced, infer subdomain using forced domain as context
                url = obj.get("meta", {}).get("data_info", {}).get("url", "")
                title = obj.get("meta", {}).get("data_info", {}).get("title", "")
                text = obj.get("text", "")
                # call infer but then override domain param by using returned subdomain
                _, subdomain = infer_domain_subdomain(url, title, text,
                                                     fallback_domain=effective_fallback_domain,
                                                     fallback_subdomain=effective_fallback_subdomain)
            else:
                url = obj.get("meta", {}).get("data_info", {}).get("url", "")
                title = obj.get("meta", {}).get("data_info", {}).get("title", "")
                text = obj.get("text", "")
                _, subdomain = infer_domain_subdomain(url, title, text,
                                                     fallback_domain=effective_fallback_domain,
                                                     fallback_subdomain=effective_fallback_subdomain)

        # set values into object
        if "meta" not in obj:
            obj["meta"] = {}
        if "content_info" not in obj["meta"]:
            obj["meta"]["content_info"] = {}
        obj["meta"]["content_info"]["domain"] = domain
        obj["meta"]["content_info"]["subdomain"] = subdomain

        # emit updated JSON line
        try:
            out_q.put(json.dumps(obj, ensure_ascii=False))
        except Exception:
            out_q.put(line.rstrip("\n"))

def reader_thread(path, in_q: Queue, stop_event: Event, num_workers: int):
    """
    Read file line-by-line and push to in_q. After EOF, push SENTINEL num_workers times.
    """
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if stop_event.is_set():
                    break
                # skip empty lines
                if not line.strip():
                    continue
                in_q.put(line)
    except Exception as e:
        # push sentinels so workers can exit
        sys.stderr.write(f"[reader] error reading {path}: {e}\n")
    finally:
        # signal workers to stop
        for _ in range(num_workers):
            in_q.put(SENTINEL)

def writer_thread(out_path, out_q: Queue, stop_event: Event, num_workers: int, progress_desc: str):
    """
    Consume processed lines from out_q and write to out_path.
    Waits for num_workers SENTINELs before finishing.
    """
    finished_workers = 0
    # open file for writing
    with open(out_path, "w", encoding="utf-8") as out_fh:
        # tqdm with no total to show records/sec
        pbar = tqdm(total=None, unit="rec", desc=progress_desc, leave=False)
        try:
            while True:
                if stop_event.is_set() and out_q.empty():
                    break
                try:
                    item = out_q.get(timeout=0.5)
                except Exception:
                    continue
                if item is SENTINEL:
                    finished_workers += 1
                    if finished_workers >= num_workers:
                        break
                    else:
                        continue
                # write processed line
                out_fh.write(item.rstrip("\n") + "\n")
                pbar.update(1)
        finally:
            pbar.close()

# ---------------------------
# Main orchestration
# ---------------------------

def process_single_file(path, args):
    """
    Process one file using multiprocessing workers, a reader thread, and a writer thread.
    """
    # determine output path
    dirpath, basename = os.path.split(path)
    name, ext = os.path.splitext(basename)
    if args.rewrite:
        if args.rewrite_path:
            out_path = args.rewrite_path
            # if rewrite_path is a directory, create file inside it
            if os.path.isdir(out_path):
                out_path = os.path.join(out_path, f"{name}_classified{ext or '.jsonl'}")
        else:
            out_path = os.path.join(dirpath or ".", f"{name}_classified{ext or '.jsonl'}")
    else:
        # modify in place: write to temp file in same directory then replace
        tmp = tempfile.NamedTemporaryFile(delete=False, dir=(dirpath or "."), prefix=f".{name}_tmp_", suffix=ext or ".jsonl")
        out_path = tmp.name
        tmp.close()

    num_workers = args.worker or cpu_count()
    # Queues for inter-process communication
    in_q = Queue(maxsize=num_workers * 4)
    out_q = Queue(maxsize=num_workers * 4)
    stop_event = Event()

    # spawn worker processes
    workers = []
    for i in range(num_workers):
        p = Process(target=worker_main, args=(
            in_q, out_q, stop_event,
            args.force_domain, args.force_subdomain,
            args.fallback_domain, args.fallback_subdomain
        ))
        p.daemon = True
        p.start()
        workers.append(p)

    # start reader and writer threads
    reader = threading.Thread(target=reader_thread, args=(path, in_q, stop_event, num_workers), daemon=True)
    writer = threading.Thread(target=writer_thread, args=(out_path, out_q, stop_event, num_workers, basename), daemon=True)

    reader.start()
    writer.start()

    try:
        # wait for reader to finish
        while reader.is_alive():
            reader.join(timeout=0.5)
        # wait for workers to finish
        for p in workers:
            p.join(timeout=0.5)
        # wait for writer to finish
        while writer.is_alive():
            writer.join(timeout=0.5)
    except KeyboardInterrupt:
        # graceful shutdown
        sys.stderr.write("\n[main] KeyboardInterrupt received, shutting down...\n")
        stop_event.set()
        # drain queues and send sentinels to ensure workers exit
        try:
            for _ in range(num_workers):
                in_q.put(SENTINEL)
        except Exception:
            pass
        # join processes
        for p in workers:
            p.terminate()
            p.join(timeout=0.5)
        writer.join(timeout=1.0)
    finally:
        # ensure all worker processes are terminated
        for p in workers:
            if p.is_alive():
                p.terminate()
                p.join(timeout=0.5)

    # if modifying in place, replace original file
    if not args.rewrite:
        try:
            shutil.move(out_path, path)
        except Exception as e:
            sys.stderr.write(f"[main] failed to replace original file: {e}\n")
            # keep temp file for inspection
            sys.stderr.write(f"[main] temp file kept at: {out_path}\n")
    else:
        sys.stderr.write(f"[main] rewritten file saved to: {out_path}\n")

def gather_input_files(paths):
    """
    Expand directories into sorted list of .jsonl files; keep files as-is.
    """
    files = []
    for p in paths:
        if os.path.isdir(p):
            for root, _, filenames in os.walk(p):
                for fn in sorted(filenames):
                    if fn.lower().endswith(".jsonl"):
                        files.append(os.path.join(root, fn))
        elif os.path.isfile(p):
            files.append(p)
        else:
            sys.stderr.write(f"[main] path not found: {p}\n")
    return files

def parse_args():
    ap = argparse.ArgumentParser(description="Stream JSONL classifier: infer domain & subdomain from url/title/text")
    ap.add_argument("paths", nargs="+", help="File or directory to process (directories expand *.jsonl).")
    ap.add_argument("--rewrite", action="store_true", help="Create a new file instead of modifying original (default: modify in place).")
    ap.add_argument("--fallback-domain", default=None, help="Fallback domain if inference fails (default: use original record value if present).")
    ap.add_argument("--fallback-subdomain", default=None, help="Fallback subdomain if inference fails (default: use original record value if present).")
    ap.add_argument("--force-domain", default=None, help="Force domain value for all records (overrides inference).")
    ap.add_argument("--force-subdomain", default=None, help="Force subdomain value for all records (overrides inference).")
    ap.add_argument("--rewrite-path", default=None, help="Path where rewrite file is saved (if --rewrite). If a directory is given, file will be created inside it.")
    ap.add_argument("--worker", type=int, default=cpu_count(), help="Number of worker processes to use (default: CPU count).")
    return ap.parse_args()

def main():
    args = parse_args()

    # Ctrl+C handler to allow graceful shutdown
    def _sigint_handler(signum, frame):
        sys.stderr.write("\n[main] SIGINT received, attempting graceful shutdown...\n")
    signal.signal(signal.SIGINT, _sigint_handler)

    files = gather_input_files(args.paths)
    if not files:
        sys.stderr.write("[main] no files to process\n")
        sys.exit(1)

    for f in files:
        sys.stderr.write(f"[main] processing: {f}\n")
        process_single_file(f, args)

if __name__ == "__main__":
    main()