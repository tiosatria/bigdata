#!/usr/bin/env python3
"""
Wrapper script to run `post_process.processor` on files inside the script's folder scope.

Features added for non-colocated processor:
 - --module-name: Python module to run with -m (default: post_process.processor)
 - --module-root: path added to PYTHONPATH so module can be imported when using -m
 - --module-file: run a python file directly (absolute or relative path)

Behavior:
 - If --module-file is provided, script runs: python /path/to/processor.py --input ... --output ...
 - Otherwise uses: python -m <module-name> with optional PYTHONPATH injection from --module-root

Usage examples:
  # module available on sys.path
  python run_processor.py cooks_com --module-name post_process.processor

  # module lives in ../repos (module root)
  python run_processor.py cooks_com --module-root "../repos"

  # run processor.py directly
  python run_processor.py cooks_com --module-file "../repos/post_process/processor.py"

"""
from __future__ import annotations
import argparse
import subprocess
import sys
import os
from pathlib import Path
from typing import List

SCRIPT_DIR = Path(__file__).resolve().parent
DEDUPED_DIR_NAME = "1_deduped"
CLEANED_DIR_NAME = "2_cleaned"
DEFAULT_INPUT_SUFFIX = "_deduped.jsonl"


def build_paths_from_name(name: str) -> (Path, Path):
    p = Path(name)
    if p.suffix:  # user passed a filename or path
        input_path = (SCRIPT_DIR / p).resolve() if not p.is_absolute() else p.resolve()
    else:
        input_path = (SCRIPT_DIR / DEDUPED_DIR_NAME / f"{name}{DEFAULT_INPUT_SUFFIX}").resolve()
    try:
        rel = input_path.relative_to(SCRIPT_DIR / DEDUPED_DIR_NAME)
        out_dir = (SCRIPT_DIR / CLEANED_DIR_NAME / rel.parent).resolve()
    except Exception:
        out_dir = (SCRIPT_DIR / CLEANED_DIR_NAME).resolve()
    return input_path, out_dir


def discover_inputs() -> List[Path]:
    deduped_root = SCRIPT_DIR / DEDUPED_DIR_NAME
    search_root = deduped_root if deduped_root.exists() else SCRIPT_DIR
    files = list(search_root.rglob("*.jsonl"))
    files.sort(key=lambda p: (not p.name.endswith(DEFAULT_INPUT_SUFFIX), str(p)))
    return files


def make_cmd(input_path: Path, out_dir: Path, forward_args: List[str], module_name: str, module_file: str) -> (List[str], dict):
    env = os.environ.copy()
    if module_file:
        # run python <module_file>
        cmd = [sys.executable, str(module_file), "--input", str(input_path), "--output", str(out_dir)]
    else:
        cmd = [sys.executable, "-m", module_name, "--input", str(input_path), "--output", str(out_dir)]
    if forward_args:
        cmd += forward_args
    return cmd, env


def run_cmd(cmd: List[str], env: dict, cwd: Path | None = None) -> int:
    print("RUN:", " ".join(cmd))
    res = subprocess.run(cmd, env=env, cwd=cwd)
    return res.returncode


def main():
    parser = argparse.ArgumentParser(description="Run post_process.processor on files inside script scope.")
    parser.add_argument("name", nargs="?", help="Basename or path to the file to process. If omitted and --auto not used, script exits.")
    parser.add_argument("--auto", action="store_true", help="Discover and process all .jsonl files under the script scope (prefers ./1_deduped)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without executing")

    # Processor location options
    parser.add_argument("--module-name", type=str, default="post_process.processor",
                        help="Module name to run with -m (default: post_process.processor)")
    parser.add_argument("--module-root", type=str,
                        help="Path to repository root containing the module; added to PYTHONPATH when invoking module with -m")
    parser.add_argument("--module-file", type=str,
                        help="Path to a processor .py file to run directly instead of using -m")

    args, forward = parser.parse_known_args()

    if not args.auto and not args.name:
        parser.error("either provide a file name or use --auto")

    # Normalize module_file if provided
    module_file = None
    if args.module_file:
        mf = Path(args.module_file)
        module_file = (SCRIPT_DIR / mf).resolve() if not mf.is_absolute() else mf.resolve()
        if not module_file.exists():
            print(f"ERROR: module file not found: {module_file}")
            sys.exit(2)

    module_root = None
    if args.module_root:
        mr = Path(args.module_root)
        module_root = (SCRIPT_DIR / mr).resolve() if not mr.is_absolute() else mr.resolve()
        if not module_root.exists():
            print(f"ERROR: module root not found: {module_root}")
            sys.exit(2)

    to_process: List[(Path, Path)] = []

    if args.auto:
        found = discover_inputs()
        for inp in found:
            try:
                rel = inp.relative_to(SCRIPT_DIR / DEDUPED_DIR_NAME)
                outdir = (SCRIPT_DIR / CLEANED_DIR_NAME / rel.parent).resolve()
            except Exception:
                outdir = (SCRIPT_DIR / CLEANED_DIR_NAME).resolve()
            to_process.append((inp.resolve(), outdir))
    else:
        input_path, out_dir = build_paths_from_name(args.name)
        to_process.append((input_path, out_dir))

    for input_path, out_dir in to_process:
        if not input_path.exists():
            print(f"SKIP missing input: {input_path}")
            continue
        out_dir.mkdir(parents=True, exist_ok=True)

        # If user provided explicit --output via forward args, we won't check guessed output
        if any(a.startswith("--output") for a in forward):
            output_exists = False
            guessed_out = None
        else:
            guessed_out = out_dir / input_path.name
            output_exists = guessed_out.exists()

        if output_exists and not args.overwrite:
            print(f"SKIP exists: {guessed_out}")
            continue

        # Build environment
        env = os.environ.copy()
        if module_root and not module_file:
            # prepend module_root to PYTHONPATH
            prev = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(module_root) + (os.pathsep + prev if prev else "")

        cmd, cmd_env = make_cmd(input_path, out_dir, forward, args.module_name, module_file)
        # merge any PYTHONPATH modification
        cmd_env.update(env)

        if args.dry_run:
            print("DRY:", " ".join(cmd))
            if module_root and not module_file:
                print("DRY: PYTHONPATH=", env.get("PYTHONPATH"))
            continue

        rc = run_cmd(cmd, cmd_env, cwd=(module_root if module_root and not module_file else None))
        if rc != 0:
            print(f"PROCESS FAILED (rc={rc}) for: {input_path}")


if __name__ == "__main__":
    main()
