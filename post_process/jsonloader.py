#!/usr/bin/env python3
"""
Unified JSON/JSONL loader utilities tailored for large datasets.
- Handles both JSON array files and JSONL files.
- Streams records in chunks to keep memory usage low.
- Provides line/record counting with tqdm progress feedback.

Intended to be reused by post-processing utilities (processor, sampler, group_dedupe, etc.).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Iterator, List, Dict, Any, Optional
from tqdm import tqdm
import sys


@dataclass
class JSONLoader:
    path: Path
    chunk_size: int = 5000
    desc: Optional[str] = None

    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path)
        if self.chunk_size <= 0:
            self.chunk_size = 5000
        if self.desc is None:
            self.desc = f"Loading {self.path.name}"

    @property
    def is_jsonl(self) -> bool:
        return self.path.suffix.lower() == ".jsonl"

    def count(self) -> int:
        """Count total records/lines for progress display.
        For JSONL: counts lines. For JSON array: loads once to get length.
        """
        try:
            if self.is_jsonl:
                with self.path.open('r', encoding='utf-8') as f:
                    return sum(1 for _ in f)
            else:
                with self.path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        return len(data)
                    raise ValueError("JSON file must contain an array of objects")
        except Exception as e:
            print(f"Error counting records in {self.path}: {e}", file=sys.stderr)
            raise

    def iter_chunks(self, limit: Optional[int] = None) -> Iterator[List[Dict[str, Any]]]:
        """Yield chunks of records as lists of dicts. Optionally limit total records yielded.
        Shows a tqdm bar for reading progress.
        """
        yielded = 0
        try:
            if self.is_jsonl:
                total = self.count()
                display_total = min(total, limit) if limit is not None else total
                with self.path.open('r', encoding='utf-8') as f, \
                        tqdm(f, total=display_total, desc=self.desc, unit=" lines", leave=False, dynamic_ncols=True) as pbar:
                    chunk: List[Dict[str, Any]] = []
                    for i, line in enumerate(pbar):
                        if limit is not None and yielded >= limit:
                            if chunk:
                                yield chunk
                            return
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line)
                        except json.JSONDecodeError as e:
                            tqdm.write(f"Warning: Skipping invalid JSON at line {i + 1}: {e}", file=sys.stderr)
                            continue
                        chunk.append(obj)
                        yielded += 1
                        if len(chunk) >= self.chunk_size:
                            yield chunk
                            chunk = []
                    if chunk:
                        yield chunk
            else:
                with self.path.open('r', encoding='utf-8') as f:
                    data = json.load(f)
                    if not isinstance(data, list):
                        raise ValueError("JSON file must contain an array of objects")
                total = len(data)
                max_count = total if limit is None else min(limit, total)
                with tqdm(total=max_count, desc=self.desc, unit=" rec", leave=False, dynamic_ncols=True) as pbar:
                    for start in range(0, max_count, self.chunk_size):
                        end = min(start + self.chunk_size, max_count)
                        chunk = data[start:end]
                        pbar.update(len(chunk))
                        yield chunk
        except Exception as e:
            print(f"Error reading {self.path}: {e}", file=sys.stderr)
            raise
