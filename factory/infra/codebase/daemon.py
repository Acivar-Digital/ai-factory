# REFERENCE ONLY — its worker functions are imported by mcp_watcher.py.
import asyncio
import hashlib
import os
import sys
import time
from pathlib import Path

from index_state import load_state
from indexer_core import index_single_file, remove_single_file
from qdrant_client import QdrantClient
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

from config import (
    CODE_EXTENSIONS,
    CODES_DIR,
    DEBOUNCE_SECONDS,
    DOCS_EXTENSIONS,
    EXCLUDE_DIRS,
    EXCLUDE_FILES,
    EXTRA_COLLECTIONS,
    INCLUDE_EXTENSIONS,
    PROJECT_ROOT,
    QDRANT_URL,
    WATCHED_REPOS,
    WATCHER_DIR,
    get_allowed_extensions,
    get_collection_dirs,
    get_collection_name,
    get_repo_root,
)

WATCHER_EXCLUDE_DIRS = EXCLUDE_DIRS | {"infra"}

# ---------------------------------------------------------------------------
# Watcher Handler (Layer 1 - Fast Path)
# ---------------------------------------------------------------------------

class AsyncIndexerHandler(FileSystemEventHandler):
    """
    Pushes valid file events into an asyncio Queue for processing.
    """
    def __init__(self, loop: asyncio.AbstractEventLoop, queue: asyncio.Queue) -> None:
        self.loop = loop
        self.queue = queue
        self.collection_map = get_collection_dirs()  # dict[display_name, (rel_path, collection_name)]

    def _get_repo_and_collection(self, path: str) -> tuple[str, str, str] | None:
        try:
            rel_path_obj = Path(path).relative_to(PROJECT_ROOT)
            p = Path(path)

            # Check extra collections first
            for extra_path, coll_name in EXTRA_COLLECTIONS.items():
                parts = extra_path.split("/")
                if len(rel_path_obj.parts) >= len(parts) and tuple(rel_path_obj.parts[:len(parts)]) == tuple(parts):
                    # Found collection root. Now check if the file is in an excluded sub-dir.
                    sub_parts = rel_path_obj.parts[len(parts):]
                    if any(sp in EXCLUDE_DIRS for sp in sub_parts):
                        return None

                    c_name = coll_name or parts[-1]
                    return extra_path, c_name, str(rel_path_obj)

            # Check standard top-level repo
            repo_name = rel_path_obj.parts[0]
            if repo_name not in WATCHER_EXCLUDE_DIRS and (PROJECT_ROOT / repo_name).is_dir():
                # Found repo root. Check if the file is in an excluded sub-dir (beyond the root).
                sub_parts = rel_path_obj.parts[1:]
                if any(sp in EXCLUDE_DIRS for sp in sub_parts):
                    return None

                # Determine collection type from file extension
                base = repo_name
                if base == "baziforecaster":
                    coll_type = "code" if p.suffix.lower() in CODE_EXTENSIONS else "docs"
                    collection_name = get_collection_name(repo_name, coll_type)
                else:
                    collection_name = repo_name
                return repo_name, collection_name, str(rel_path_obj)

            return None
        except (ValueError, IndexError):
            return None

    def _should_handle(self, src_path: str) -> bool:
        p = Path(src_path)
        if p.name in EXCLUDE_FILES:
            return False
        if p.suffix.lower() == ".json" and CODES_DIR in p.parents:
            return False
        return p.suffix.lower() in INCLUDE_EXTENSIONS

    def _push_event(self, action: str, src_path: str) -> None:
        if not self._should_handle(src_path):
            return
        result = self._get_repo_and_collection(src_path)
        if result:
            repo_name, collection_name, rel_path = result
            # Calculate the path relative to the repo root for indexing
            repo_root = get_repo_root(repo_name)
            try:
                repo_rel_path = str(Path(src_path).relative_to(repo_root))
            except ValueError:
                repo_rel_path = rel_path # fallback

            # enqueue as (action, repo_name, collection_name, repo_rel_path)
            self.loop.call_soon_threadsafe(
                self.queue.put_nowait,
                (action, repo_name, collection_name, repo_rel_path)
            )

    def on_modified(self, event):
        if not event.is_directory:
            self._push_event("upsert", event.src_path)

    def on_created(self, event):
        if not event.is_directory:
            self._push_event("upsert", event.src_path)

    def on_deleted(self, event):
        if not event.is_directory:
            self._push_event("delete", event.src_path)

    def on_moved(self, event):
        if not event.is_directory:
            self._push_event("delete", event.src_path)
            self._push_event("upsert", event.dest_path)


# ---------------------------------------------------------------------------
# Layer 1 Worker
# ---------------------------------------------------------------------------
async def watcher_worker(queue: asyncio.Queue):
    """Consume events from watchdog and apply to Qdrant/state."""
    print("Layer 1 (Watcher) worker started.")

    # We use a simple debounce buffer per file to avoid thrashing on rapid saves
    pending_tasks = {}

    while True:
        try:
            # Get an item, wait if queue is empty
            item = await asyncio.wait_for(queue.get(), timeout=1.0)
            action, repo, collection, rel_path = item

            # Simple debounce key
            key = (collection, rel_path)
            pending_tasks[key] = (action, repo, time.time())
            queue.task_done()

        except TimeoutError:
            # Every second, process tasks that have "cooled down"
            now = time.time()
            to_process = []
            for key, (action, repo, timestamp) in list(pending_tasks.items()):
                if now - timestamp >= DEBOUNCE_SECONDS:
                    to_process.append((key, action, repo))
                    del pending_tasks[key]

            for (collection, rel_path), action, repo in to_process:
                print(f"[Watcher] Processing {action}: {rel_path} in {collection}")
                if action == "upsert":
                    await index_single_file(repo, collection, rel_path)
                elif action == "delete":
                    await remove_single_file(collection, rel_path)

                # Verify after change
                await verify_single_file(collection, rel_path, action)

# ---------------------------------------------------------------------------
# Verification Logic
# ---------------------------------------------------------------------------
async def verify_single_file(collection: str, rel_path: str, expected_action: str):
    """Confirm a specific file's state in Qdrant matches expectations."""
    try:
        from qdrant_client.models import FieldCondition, Filter, MatchValue
        client = QdrantClient(url=QDRANT_URL)
        res = client.scroll(
            collection_name=collection,
            scroll_filter=Filter(must=[FieldCondition(key="file_path", match=MatchValue(value=rel_path))]),
            limit=1,
            with_payload=False,
            with_vectors=False
        )
        exists = len(res[0]) > 0
        if expected_action == "upsert" and not exists:
            print(f"[Validator ERROR] File {rel_path} should be upserted but is missing from {collection}!")
        elif expected_action == "delete" and exists:
            print(f"[Validator ERROR] File {rel_path} should be deleted but exists in {collection}!")
    except Exception as e:
        print(f"[Validator WARN] Could not verify {rel_path}: {e}")

# ---------------------------------------------------------------------------
# Layer 2 - Reconciler
# ---------------------------------------------------------------------------
def _get_include_dirs(repo_name: str) -> list[str]:
    from config import STANDARD_DIRS
    if repo_name in EXTRA_COLLECTIONS:
        return ["."]
    return STANDARD_DIRS

async def reconciler_task():
    """Periodically scan filesystem and fix drift."""
    print("Layer 2 (Reconciler) started.")

    # Run immediately on start, then every 5 minutes
    while True:
        print("\n[Reconciler] Starting reconciliation scan...")

        collections = get_collection_dirs()
        for display_name, (rel_path, coll_name) in collections.items():
            repo_name = rel_path
            repo_root = get_repo_root(repo_name)
            include_dirs = _get_include_dirs(repo_name)

            allowed_exts = get_allowed_extensions(coll_name)
            state = load_state(coll_name)
            fs_files = set()

            # Scan filesystem
            for include_dir in include_dirs:
                dir_path = repo_root / include_dir
                if not dir_path.exists():
                    continue

                for root, dirs, files in os.walk(dir_path):
                    dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                    for f in files:
                        file_path = Path(root) / f
                        if file_path.suffix.lower() not in allowed_exts:
                            continue
                        if file_path.name in EXCLUDE_FILES:
                            continue
                        if file_path.suffix.lower() == ".json" and CODES_DIR in file_path.parents:
                            continue

                        try:
                            file_rel = str(file_path.resolve().relative_to(repo_root))
                            fs_files.add(file_rel)

                            mtime = file_path.stat().st_mtime
                            size = file_path.stat().st_size

                            needs_update = False
                            cached = state.get(file_rel)
                            if not cached:
                                needs_update = True
                            elif cached["mtime"] != mtime or cached["size"] != size:
                                # Re-hash to be sure
                                content = file_path.read_text(encoding="utf-8")
                                current_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                                if current_hash != cached["hash"]:
                                    needs_update = True
                                else:
                                    # Update state with new mtime/size even if hash didn't change (e.g. touch)
                                    from index_state import update_file_state
                                    update_file_state(coll_name, file_rel, current_hash, mtime, size)

                            if needs_update:
                                print(f"[Reconciler] Drift detected (upsert): {file_rel}")
                                await index_single_file(repo_name, coll_name, file_rel)

                        except Exception as e:
                            print(f"[Reconciler WARN] Failed to process {file_path}: {e}")

            # Check for deletions (in state but not on fs)
            for cached_file in list(state.keys()):
                if cached_file not in fs_files:
                    print(f"[Reconciler] Drift detected (delete): {cached_file}")
                    await remove_single_file(coll_name, cached_file)

        print("[Reconciler] Scan complete.")
        await asyncio.sleep(300)  # Every 5 minutes

# ---------------------------------------------------------------------------
# Layer 3 - Validator
# ---------------------------------------------------------------------------
async def validator_task():
    """Periodically ensure Qdrant matches the filesystem/state."""
    print("Layer 3 (Validator) started.")
    await asyncio.sleep(60) # Stagger start

    while True:
        print("\n[Validator] Starting full Qdrant verification...")
        try:
            client = QdrantClient(url=QDRANT_URL)
            collections = get_collection_dirs()

            for display_name, (rel_path, coll_name) in collections.items():
                existing_cols = [c.name for c in client.get_collections().collections]
                if coll_name not in existing_cols:
                    continue

                # Scroll Qdrant to get all indexed paths
                offset = None
                qdrant_paths = set()
                while True:
                    res, next_offset = client.scroll(
                        collection_name=coll_name,
                        limit=1000,
                        offset=offset,
                        with_payload=["file_path"],
                        with_vectors=False
                    )
                    for pt in res:
                        qdrant_paths.add(pt.payload.get("file_path"))
                    offset = next_offset
                    if offset is None:
                        break

                # Load local state
                state = load_state(coll_name)
                # Only expect files with non-zero size to be in Qdrant
                state_paths = {p for p, data in state.items() if data.get("size", 0) > 0}

                # Compare
                missing_in_qdrant = state_paths - qdrant_paths
                extra_in_qdrant = qdrant_paths - state_paths

                if missing_in_qdrant or extra_in_qdrant:
                    print(f"[Validator ERROR] Qdrant vs State mismatch in '{coll_name}'!")
                    if missing_in_qdrant:
                        print(f"  Missing in Qdrant: {len(missing_in_qdrant)} files")
                        # Force reconciliation
                        for mf in missing_in_qdrant:
                            from index_state import remove_file_state
                            remove_file_state(coll_name, mf) # Remove from state so reconciler picks it up
                    if extra_in_qdrant:
                        print(f"  Extra in Qdrant: {len(extra_in_qdrant)} files")
                        for ef in extra_in_qdrant:
                            await remove_single_file(coll_name, ef)
                else:
                    print(f"[Validator] '{coll_name}' Qdrant == State. OK.")

        except Exception as e:
            print(f"[Validator ERROR] Validation failed: {e}")

        await asyncio.sleep(600) # Every 10 minutes

# ---------------------------------------------------------------------------
# Layer 4 - Full Scan
# ---------------------------------------------------------------------------

def get_all_repos() -> list[str]:
    repos: list[str] = list(WATCHED_REPOS)
    for rel_path in EXTRA_COLLECTIONS:
        repos.append(rel_path)
    return repos

def get_repo_collection_names(repo_name: str) -> list[tuple[str, set[str]]]:
    """Return list of (collection_name, allowed_extensions) for a repo.

    For baziforecaster, returns both _code and _docs entries.
    For other repos, returns a single entry with all extensions.
    """
    base = repo_name.split("/")[-1]
    if base == "baziforecaster":
        return [
            (get_collection_name(repo_name, "code"), CODE_EXTENSIONS),
            (get_collection_name(repo_name, "docs"), DOCS_EXTENSIONS),
        ]
    if repo_name in EXTRA_COLLECTIONS:
        explicit = EXTRA_COLLECTIONS[repo_name]
        coll = explicit or base
        return [(coll, INCLUDE_EXTENSIONS)]
    return [(repo_name, INCLUDE_EXTENSIONS)]

async def run_full_scan() -> None:
    """Run indexer for ALL repos every 60 minutes (change of guard)."""
    # Local TEI only — cloud/OpenRouter fallback removed.
    from indexer_local import run_indexer

    print(f"\n{'='*50}")
    print(f"  FULL SCAN (change of guard) — {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*50}")
    for repo in get_all_repos():
        for collection, allowed_exts in get_repo_collection_names(repo):
            print(f"\n  Full-scan indexing: {repo} -> {collection}")
            try:
                await run_indexer(
                    repo_name=repo,
                    collection_name=collection,
                    reset=False,
                    allowed_extensions=allowed_exts,
                )
            except Exception as e:
                print(f"  Full-scan error for {repo}: {e}")
    print(f"{'='*50}")
    print("  FULL SCAN COMPLETE")
    print(f"{'='*50}\n")

async def full_scan_task():
    """Periodic full scan every 60 minutes."""
    full_scan_interval = 3600  # 60 minutes
    print("Layer 4 (Full Scan) started. Scanning every 60 minutes.")
    await asyncio.sleep(30)  # Stagger start
    while True:
        await run_full_scan()
        await asyncio.sleep(full_scan_interval)


async def graph_build_task():
    """Rebuild knowledge graphs every 5 minutes."""
    interval = 300  # 5 minutes
    print("Graph Builder started. Rebuilding every 5 minutes.")
    await asyncio.sleep(60)
    while True:
        print(f"\n{'='*50}")
        print(f"  GRAPH BUILD — {time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*50}")
        for script in ["code_graph.py", "doc_graph.py"]:
            script_path = WATCHER_DIR / script
            if not script_path.exists():
                print(f"  [Graph] Script not found: {script_path}")
                continue
            print(f"  [Graph] Running {script} --build...")
            proc = await asyncio.create_subprocess_exec(
                "uv", "run", str(script_path), "--build",
                cwd=WATCHER_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if stdout:
                print(stdout.decode().rstrip())
            if stderr:
                print(f"  [Graph] stderr: {stderr.decode().rstrip()}")
            if proc.returncode != 0:
                print(f"  [Graph ERROR] {script} exited with code {proc.returncode}")
        print(f"{'='*50}\n")
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Main Daemon
# ---------------------------------------------------------------------------
async def run_daemon():
    # Kill any existing old watchers
    try:
        import psutil
        current_pid = os.getpid()
        # Find all ancestor PIDs to avoid killing our own wrappers
        ancestry = set()
        try:
            curr = psutil.Process(current_pid)
            while curr is not None:
                ancestry.add(curr.pid)
                curr = curr.parent()
        except Exception:
            ancestry.add(current_pid)

        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                cmdline = ' '.join(proc.info['cmdline'] or [])
                if ('watcher.py' in cmdline or 'daemon.py' in cmdline) and proc.info['pid'] not in ancestry:
                    print(f"Killing existing daemon (PID: {proc.info['pid']})...")
                    proc.kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
    except ImportError:
        pass

    loop = asyncio.get_running_loop()
    queue = asyncio.Queue()

    event_handler = AsyncIndexerHandler(loop, queue)
    observer = Observer()

    watched_count = 0
    for repo_name in WATCHED_REPOS:
        repo_path = PROJECT_ROOT / repo_name
        if repo_path.is_dir():
            observer.schedule(event_handler, str(repo_path), recursive=True)
            watched_count += 1

    for rel_path in EXTRA_COLLECTIONS:
        extra_path = PROJECT_ROOT / rel_path
        if extra_path.is_dir():
            observer.schedule(event_handler, str(extra_path), recursive=True)
            watched_count += 1

    if watched_count == 0:
        print("Error: no watched directories found.")
        sys.exit(1)

    observer.start()
    print(f"\nTruth Convergence Indexing Daemon started. Watching {watched_count} repo(s).")

    # Start tasks
    worker_task = asyncio.create_task(watcher_worker(queue))
    recon_task = asyncio.create_task(reconciler_task())
    val_task = asyncio.create_task(validator_task())
    full_scan = asyncio.create_task(full_scan_task())
    graph_task = asyncio.create_task(graph_build_task())

    try:
        # Keep running
        await asyncio.gather(worker_task, recon_task, val_task, full_scan, graph_task)
    except asyncio.CancelledError:
        pass
    finally:
        observer.stop()
        observer.join()

def main():
    try:
        asyncio.run(run_daemon())
    except KeyboardInterrupt:
        print("\nDaemon stopped.")

if __name__ == "__main__":
    main()
