#!/usr/bin/env python3
"""CLI shadow tool to scan Python files for Cyclomatic Complexity (CC > 5),
deep nesting (depth > 3), and try pyramids.
"""

import argparse
import ast
import json
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from factory.infra.ast_analyzer import FunctionCandidateScanner  # noqa: E402
from factory.tools._codebase_common import resolve_secure_path  # noqa: E402


def scan_file(file_path: Path) -> list[dict]:
    try:
        source = file_path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(file_path))
    except Exception:
        return []

    lines = source.splitlines()
    scanner = FunctionCandidateScanner(
        filename=str(file_path),
        code_lines=lines,
        full_file_source=source,
    )
    scanner.visit(tree)
    return scanner.candidates


def get_python_files(target_path: Path) -> list[Path]:
    if target_path.is_file():
        return [target_path] if target_path.suffix == ".py" else []

    ignore_dirs = {".git", "__pycache__", ".pytest_cache", "node_modules", "venv", ".venv", "temp"}
    py_files: list[Path] = []

    for dirpath, dirnames, filenames in os.walk(target_path):
        dirnames[:] = [d for d in dirnames if d not in ignore_dirs]
        for fname in filenames:
            if fname.endswith(".py"):
                py_files.append(Path(dirpath) / fname)

    return sorted(py_files)


def main():
    parser = argparse.ArgumentParser(
        description="Scan Python codebase for CC > 5, nesting > 3, and try-pyramid violations."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        default=["src2"],
        help="Target files or directories to scan (default: src2)",
    )
    parser.add_argument(
        "--min-cc",
        type=int,
        default=6,
        help="Minimum CC to report as violation (default: 6, meaning CC > 5)",
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="Maximum allowed nesting depth (default: 3)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output raw JSON instead of human-readable report",
    )

    args = parser.parse_args()

    files_to_scan: list[Path] = []
    for raw_path in args.paths:
        resolved = resolve_secure_path(raw_path)
        if resolved.exists():
            files_to_scan.extend(get_python_files(resolved))

    # Deduplicate paths
    files_to_scan = sorted(list(set(files_to_scan)))

    all_candidates: list[dict] = []
    for fpath in files_to_scan:
        all_candidates.extend(scan_file(fpath))

    # Filter according to user thresholds
    filtered = [
        c
        for c in all_candidates
        if c["cc"] >= args.min_cc or c["max_depth"] > args.max_depth or len(c["try_issues"]) > 0
    ]

    if args.json:
        print(json.dumps(filtered, indent=2))
        sys.exit(0 if len(filtered) == 0 else 1)

    print(f"\n{'=' * 75}")
    print(f"  Code Hygiene Scanner — CC >= {args.min_cc} | Nesting > {args.max_depth} | Try Pyramids")
    print(f"{'=' * 75}\n")

    if not filtered:
        print(f"  [OK] Zero violations found across {len(files_to_scan)} Python file(s).\n")
        sys.exit(0)

    print(f"  {'CC':<5} {'Depth':<7} {'Line':<8} {'Function':<30} {'File'}")
    print(f"  {'-' * 4} {'-' * 6} {'-' * 7} {'-' * 29} {'-' * 25}")

    for c in filtered:
        rel_file = c['file_path']
        print(f"  {c['cc']:<5} {c['max_depth']:<7} {c['line']:<8} {c['function_name']:<30} {rel_file}")
        if c["try_issues"]:
            for issue_line, issue_desc in c["try_issues"]:
                print(f"        └─ [Try Pyramid] line {issue_line}: {issue_desc}")

    print(f"\n{'=' * 75}")
    print(f"  Scanned {len(files_to_scan)} file(s) — Total Violations: {len(filtered)}")
    print(f"{'=' * 75}\n")

    sys.exit(1 if len(filtered) > 0 else 0)


if __name__ == "__main__":
    main()
