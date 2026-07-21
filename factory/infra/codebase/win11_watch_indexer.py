import platform
import subprocess
import sys
import time
from pathlib import Path

from watchdog.events import FileSystemEventHandler

# Use Windows-native API observer on Win11, fallback to standard on others
if platform.system() == "Windows":
    from watchdog.observers.read_directory_changes import WindowsApiObserver as Observer
else:
    from watchdog.observers import Observer

# Configuration (mirrors indexer.py)
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
INDEXER_SCRIPT = Path(__file__).parent / "indexer.py"

INCLUDE_DIRS = [
    "src",
    "docs",
    "tests",
    "alt_src",
    "_docs",
    "test",
    "tools",
    "config",
    "User",
    "DEV",
    "PM",
    "coverage_html",
    "scratch",
    "admin",
    "REVIEW",
]
INCLUDE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".bat",
    ".ps1",
    ".sh",
    ".ts",
    ".html",
    ".htm",
}
DEBOUNCE_SECONDS = 2.0


class IndexerHandler(FileSystemEventHandler):
    def __init__(self) -> None:
        self.pending_change = False

    def _should_handle(self, src_path: str) -> bool:
        return Path(src_path).suffix.lower() in INCLUDE_EXTENSIONS

    def on_modified(self, event) -> None:
        if not event.is_directory and self._should_handle(event.src_path):
            print(f"Modified: {event.src_path}")
            self.pending_change = True

    def on_created(self, event) -> None:
        if not event.is_directory and self._should_handle(event.src_path):
            print(f"Created:  {event.src_path}")
            self.pending_change = True

    def on_deleted(self, event) -> None:
        if not event.is_directory and self._should_handle(event.src_path):
            print(f"Deleted:  {event.src_path}")
            self.pending_change = True


def run_indexer() -> None:
    """Invoke indexer.py using the same Python interpreter (works on Win11 + uv)."""
    print("--- Triggering Codebase Indexer ---")
    try:
        subprocess.run(
            [sys.executable, str(INDEXER_SCRIPT)],
            cwd=str(PROJECT_ROOT),
            check=True,
        )
        print("--- Indexing Complete ---")
    except subprocess.CalledProcessError as e:
        print(f"Indexer error (exit {e.returncode})")
    except Exception as e:
        print(f"Unexpected error: {e}")


def main() -> None:
    event_handler = IndexerHandler()
    observer = Observer()

    watched_count = 0
    for dir_name in INCLUDE_DIRS:
        dir_path = PROJECT_ROOT / dir_name
        if dir_path.exists():
            observer.schedule(event_handler, str(dir_path), recursive=True)
            watched_count += 1

    if watched_count == 0:
        print("Error: no watched directories found under project root.")
        sys.exit(1)

    print(f"Watching {watched_count} director(ies) for changes...")
    print(f"Platform: {platform.system()} | Observer: {type(observer).__name__}")
    print("Press Ctrl+C to stop.\n")

    observer.start()
    try:
        while True:
            time.sleep(0.5)
            if event_handler.pending_change:
                # Debounce: wait for burst of saves to settle
                time.sleep(DEBOUNCE_SECONDS)
                event_handler.pending_change = False
                run_indexer()
    except KeyboardInterrupt:
        print("\nStopping watcher...")
        observer.stop()
    observer.join()


if __name__ == "__main__":
    main()
