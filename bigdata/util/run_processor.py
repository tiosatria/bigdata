#!/usr/bin/env python3
"""
Wrapper script to run `post_process.processor` on files inside the script's folder scope.

Features:
 - Accept a filename basename (e.g. cooks_com) or a full filename (e.g. cooks_com_deduped.jsonl)
 - Build input path from ./1_deduped and output path to ./2_cleaned by default
 - --auto: discover and process all .jsonl files (prefers files in 1_deduped if present) recursively
 - Forwards unknown args directly to the processor module
 - Skips processing when output already exists unless --overwrite is passed
 - Can run module via -m (module name) or by executing a module file directly
 - If --module-root is omitted, will fall back to the environment variable POST_PROCESS_MODULE_ROOT

Usage examples:
  # module available on sys.path
  python run_processor.py cooks_com --module-name post_process.processor

  # module root provided via env var (preferred for convenience)
  export POST_PROCESS_MODULE_ROOT=/home/user/repos
  python run_processor.py cooks_com

  # or provide module root explicitly
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
ENV_MODULE_ROOT_NAME = "POST_PROCESS_MODULE_ROOT"


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


def resolve_module_root(cli_root: str | None) -> Path | None:
    if cli_root:
        mr = Path(cli_root)
        resolved = (SCRIPT_DIR / mr).resolve() if not mr.is_absolute() else mr.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"module root not found: {resolved}")
        return resolved
    env_val = os.environ.get(ENV_MODULE_ROOT_NAME)
    if env_val:
        mr = Path(env_val)
        resolved = (SCRIPT_DIR / mr).resolve() if not mr.is_absolute() else mr.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"env {ENV_MODULE_ROOT_NAME} points to missing path: {resolved}")
        return resolved
    return None


def main():
    parser = argparse.ArgumentParser(description="Run post_process.processor on files inside script scope.")
    parser.add_argument("--name", "-n", type=str, help="Basename or path to the file to process. If omitted and --auto not used, script exits.")
    parser.add_argument("--auto", action="store_true", help="Discover and process all .jsonl files under the script scope (prefers ./1_deduped)")
    parser.add_argument("--overwrite", action="store_true", help="Overwrite existing outputs")
    parser.add_argument("--dry-run", action="store_true", help="Show commands without executing")

    parser.add_argument("--module-name", type=str, default="post_process.processor",
                        help="Module name to run with -m (default: post_process.processor)")
    parser.add_argument("--module-root", type=str,
                        help=f"Path to repository root containing the module; added to PYTHONPATH when invoking module with -m. If omitted, checks env var {ENV_MODULE_ROOT_NAME}.")
    parser.add_argument("--module-file", type=str,
                        help="Path to a processor .py file to run directly instead of using -m")

    args, forward = parser.parse_known_args()

    if not args.auto and not args.name:
        parser.error("either provide a file name with --name (or -n) or use --auto")

    try:
        module_root = resolve_module_root(args.module_root)
    except FileNotFoundError as e:
        print("ERROR:", e)
        sys.exit(2)

    module_file = None
    if args.module_file:
        mf = Path(args.module_file)
        module_file = (SCRIPT_DIR / mf).resolve() if not mf.is_absolute() else mf.resolve()
        if not module_file.exists():
            print(f"ERROR: module file not found: {module_file}")
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

        # Determine final output path (file, not dir)
        if any(a.startswith("--output") for a in forward):
            output_exists = False
            guessed_out = None
            final_output = None
        else:
            base_name = input_path.stem.replace("_deduped", "_cleaned") + ".jsonl"
            final_output = out_dir / base_name
            output_exists = final_output.exists()

        if output_exists and not args.overwrite:
            print(f"SKIP exists: {final_output}")
            continue

        env = os.environ.copy()
        if module_root and not module_file:
            prev = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = str(module_root) + (os.pathsep + prev if prev else "")

        # If output not overridden, pass the full output path instead of folder
        if final_output:
            cmd_output_arg = str(final_output)
        else:
            cmd_output_arg = str(out_dir)

        cmd, cmd_env = make_cmd(input_path, cmd_output_arg, forward, args.module_name, module_file)
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
