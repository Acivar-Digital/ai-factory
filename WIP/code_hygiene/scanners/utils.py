import os
import subprocess
import sys
from pathlib import Path


def get_src2_files() -> list[Path]:
    """Get all Python files under src2 that are not ignored by git, or override via env."""
    use_diff = False
    if "--diff" in sys.argv:
        use_diff = True
        sys.argv.remove("--diff")

    if "HYGIENE_FILES_TO_SCAN" in os.environ:
        paths_str = os.environ["HYGIENE_FILES_TO_SCAN"]
        if not paths_str:
            return []
        return [Path(p.strip()) for p in paths_str.split(",") if p.strip()]

    if use_diff:
        try:
            changed_files = set()
            # 1. Uncommitted (staged + unstaged) changes
            res1 = subprocess.run(["git", "diff", "--name-only", "HEAD"], capture_output=True, text=True)
            if res1.returncode == 0:
                changed_files.update(res1.stdout.strip().split("\n"))
            # 2. Untracked files
            res2 = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], capture_output=True, text=True)
            if res2.returncode == 0:
                changed_files.update(res2.stdout.strip().split("\n"))

            paths = []
            for line in sorted(changed_files):
                line = line.strip()
                if not line:
                    continue
                path = Path(line)
                if path.parts and path.parts[0] == "src2" and path.suffix == ".py" and path.name != "__init__.py":
                    if path.is_file():
                        paths.append(path)
            return paths
        except Exception as e:
            print(f"Error getting git diff files: {e}", file=sys.stderr)
            return []

    try:
        result = subprocess.run(
            ["git", "ls-files", "--cached", "--others", "--exclude-standard", "src2"],
            capture_output=True,
            text=True,
            check=True,
        )
        paths = [Path(line.strip()) for line in result.stdout.strip().split("\n") if line.strip()]
        return [p for p in paths if p.is_file() and p.suffix == ".py" and p.name != "__init__.py"]
    except Exception as e:
        print(f"Error getting git files: {e}", file=sys.stderr)
        # Fallback to recursively walking src2 excluding __pycache__
        return [
            p
            for p in Path("src2").rglob("*.py")
            if p.is_file() and p.name != "__init__.py" and "__pycache__" not in p.parts
        ]


def is_binary_file(file_path: Path) -> bool:
    """Check if a file is binary by searching for null bytes."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            return b"\x00" in chunk
    except Exception:
        return False
