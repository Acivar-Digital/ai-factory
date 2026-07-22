import argparse
import json
import sys
from pathlib import Path

from _codebase_common import EXCLUDE_DIRS, fail, ok, resolve_secure_path

sys.path.append(str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description="Return an ASCII tree of the project structure.")
    parser.add_argument("--max-depth", type=int, default=4, help="How many directory levels to show.")
    args = parser.parse_args()

    try:
        lines: list[str] = []

        def _tree(path: Path, prefix: str, depth: int) -> None:
            if depth > args.max_depth:
                return
            try:
                entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name))
            except PermissionError:
                return
            entries = [e for e in entries if e.name not in EXCLUDE_DIRS]
            for i, entry in enumerate(entries):
                connector = "└── " if i == len(entries) - 1 else "├── "
                lines.append(f"{prefix}{connector}{entry.name}" + ("/" if entry.is_dir() else ""))
                if entry.is_dir():
                    extension = "    " if i == len(entries) - 1 else "│   "
                    _tree(entry, prefix + extension, depth + 1)

        tree_root = resolve_secure_path(".").resolve()
        lines.append(f"{tree_root.name}/")
        _tree(tree_root, "", 1)
        tree_str = "\n".join(lines)
        print(json.dumps(ok(
            f"Project structure at {tree_root} (depth={args.max_depth})",
            {"structure": tree_str},
        ), indent=2, ensure_ascii=False))
    except Exception as e:
        print(json.dumps(fail(f"Failed to get repo structure: {e}"), indent=2))


if __name__ == "__main__":
    main()
