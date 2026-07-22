import argparse
import json
import shutil
import sys
from pathlib import Path

from _codebase_common import fail, ok, resolve_repo_path

sys.path.append(str(Path(__file__).resolve().parents[1]))


def main():
    parser = argparse.ArgumentParser(description="Delete a file or directory from the repo.")
    parser.add_argument("relative_path", help="Path to file or directory to delete.")
    args = parser.parse_args()

    try:
        path = resolve_repo_path(args.relative_path)
    except ValueError as e:
        print(json.dumps(fail(str(e)), indent=2))
        sys.exit(1)

    if not path.exists():
        print(json.dumps(fail(f"File not found: {args.relative_path}"), indent=2))
        sys.exit(1)

    try:
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        print(json.dumps(ok(f"Deleted {args.relative_path}", {"path": args.relative_path}), indent=2))
    except Exception as e:
        print(json.dumps(fail(f"delete_file failed: {e}"), indent=2))
        sys.exit(1)


if __name__ == "__main__":
    main()
