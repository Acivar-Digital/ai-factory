# infra/codebase/mcp_watcher.py
#
# Embedded file-watcher + startup dependency preflight for the codebase MCP servers.
# Imported by mcp_codebase.py (scope="code", run_graph_build=True) and
# mcp_docs.py (scope="docs", run_graph_build=False).
#
# All diagnostics go to STDERR — stdout is the FastMCP JSON-RPC pipe and must stay clean.

import asyncio
import os
import sys
import time
import threading
import atexit
import httpx
from pathlib import Path

# This deployment runs the user's own local BGEM3/TEI server (BGEM3_URL),
# NOT OpenRouter cloud. Force local embedding mode BEFORE importing
# indexer_core/daemon, which read EMBEDDING_MODE at import time. Use setdefault
# so an explicit EMBEDDING_MODE in the launch env still wins.
os.environ.setdefault("EMBEDDING_MODE", "local")

from watchdog.observers import Observer
from qdrant_client import QdrantClient

from config import (
    QDRANT_URL, BGEM3_URL, BGEM3_TOKEN, WATCHED_REPOS,
    EXTRA_COLLECTIONS, PROJECT_ROOT, WATCHER_DIR, DEBOUNCE_SECONDS,
)
from indexer_core import ensure_collection, index_single_file, remove_single_file

from daemon import (
    AsyncIndexerHandler, reconciler_task, validator_task,
    verify_single_file,
)
from code_graph import get_graph_paths as get_code_graph_paths
from doc_graph import get_graph_paths as get_doc_graph_paths


def eprint(*args, **kwargs):
    """Print diagnostics to stderr to avoid FastMCP stdout JSON-RPC corruption."""
    kwargs["file"] = sys.stderr
    print(*args, **kwargs)


# ---------------------------------------------------------------------------
# Startup dependency preflight
# ---------------------------------------------------------------------------

def run_preflight(collection_names: list[str], service_name: str) -> bool:
    """Verify Qdrant + BGEM3/TEI are reachable and collections exist.

    Returns False if any requirement is missing. Caller should sys.exit(1).
    All output goes to stderr.
    """
    eprint(f"[preflight] Checking dependencies for {service_name} MCP server...")
    success = True
    client = None

    # 1. Qdrant
    try:
        client = QdrantClient(url=QDRANT_URL, timeout=5.0, check_compatibility=False)
        client.get_collections()
        eprint("✅ Qdrant reachable")
    except Exception as e:
        eprint(f"❌ Qdrant unreachable at {QDRANT_URL}: {e}")
        success = False

    # 2. BGEM3 / TEI embedding service (OpenAI-compatible /v1/embeddings)
    try:
        headers = {"Authorization": f"Bearer {BGEM3_TOKEN}"} if BGEM3_TOKEN else {}
        resp = httpx.post(BGEM3_URL, json={"input": ["ping"]}, headers=headers, timeout=5.0)
        resp.raise_for_status()
        eprint("✅ BGEM3/TEI reachable")
    except Exception as e:
        eprint(f"❌ BGEM3/TEI embedding service unreachable at {BGEM3_URL}: {e}")
        success = False

    if not success:
        eprint(f"Refusing to start {service_name} MCP server — required dependencies missing.")
        return False

    # 3. Collections exist (create if missing)
    try:
        for name in collection_names:
            ensure_collection(client, name)
        eprint("✅ collections ready")
    except Exception as e:
        eprint(f"❌ Cannot create/access collection '{name}': {e}")
        eprint(f"Refusing to start {service_name} MCP server — required dependencies missing.")
        return False

    return True


# ---------------------------------------------------------------------------
# Embedded watcher worker (replaces daemon.watcher_worker; adds scope + dirty)
# ---------------------------------------------------------------------------

async def embedded_worker(queue: asyncio.Queue, scope: str):
    """Consume filesystem events, reindex into Qdrant, and flag graphs dirty."""
    pending_tasks: dict = {}
    while True:
        try:
            item = await asyncio.wait_for(queue.get(), timeout=1.0)
            action, repo, collection, rel_path = item

            # Scope filter — prevent mcp_docs from indexing code and vice-versa
            if scope == "code" and collection.endswith("_docs"):
                queue.task_done()
                continue
            if scope == "docs" and collection.endswith("_code"):
                queue.task_done()
                continue

            pending_tasks[(collection, rel_path)] = (action, repo, time.time())
            queue.task_done()

        except asyncio.TimeoutError:
            now = time.time()
            to_process = []
            for key, (action, repo, timestamp) in list(pending_tasks.items()):
                if now - timestamp >= DEBOUNCE_SECONDS:
                    to_process.append((key, action, repo))
                    del pending_tasks[key]

            for (collection, rel_path), action, repo in to_process:
                eprint(f"[EmbeddedWatcher] Processing {action}: {rel_path} in {collection}")
                success = False
                if action == "upsert":
                    success = await index_single_file(repo, collection, rel_path)
                elif action == "delete":
                    await remove_single_file(collection, rel_path)
                    success = True

                await verify_single_file(collection, rel_path, action)

                # Flag the respective knowledge graph as dirty on successful change
                if success:
                    try:
                        if collection.endswith("_docs"):
                            _, dirty = get_doc_graph_paths(collection)
                        else:
                            _, dirty = get_code_graph_paths(collection)
                        dirty.parent.mkdir(parents=True, exist_ok=True)
                        dirty.touch()
                    except Exception as e:
                        eprint(f"[EmbeddedWatcher ERROR] Failed setting dirty marker: {e}")


# ---------------------------------------------------------------------------
# Startup graph freshness
# ---------------------------------------------------------------------------

def _graph_is_stale(json_path: "Path", roots: list) -> bool:
    """Mirror graph_health staleness: graph older than any watched py/md file."""
    if not json_path.exists():
        return True
    try:
        mtime = json_path.stat().st_mtime
    except OSError:
        return True
    exts = (".py", ".md", ".json", ".yaml", ".yml", ".toml", ".ts", ".html", ".sql", ".sh")
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", ".venv", "node_modules"}]
            for f in files:
                if f.endswith(exts):
                    try:
                        if (Path(dirpath) / f).stat().st_mtime > mtime:
                            return True
                    except OSError:
                        continue
    return False


async def ensure_fresh_graphs():
    """Rebuild graphs at cold boot if dirty OR stale (mtime older than watched files)."""
    code_json, code_dirty = get_code_graph_paths("baziforecaster_code")
    doc_json, doc_dirty = get_doc_graph_paths("baziforecaster_docs")

    async def run_build(script: str):
        eprint(f"[EmbeddedWatcher] Running initial graph build: {script}")
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, script, "--build",
                cwd=WATCHER_DIR,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
            if proc.returncode != 0:
                eprint(f"[EmbeddedWatcher ERROR] {script} failed:\n{stderr.decode()}")
            else:
                eprint(f"[EmbeddedWatcher] {script} build complete.")
        except Exception as e:
            eprint(f"[EmbeddedWatcher ERROR] {script} could not run: {e}")

    watched_roots = [PROJECT_ROOT / r for r in WATCHED_REPOS] + \
                   [PROJECT_ROOT / p for p in EXTRA_COLLECTIONS]

    if code_dirty.exists() or _graph_is_stale(code_json, watched_roots):
        await run_build("code_graph.py")
    if doc_dirty.exists() or _graph_is_stale(doc_json, watched_roots):
        await run_build("doc_graph.py")


# ---------------------------------------------------------------------------
# Periodic graph rebuild (every 30 min) — uses the running venv python
# (the MCP process is launched via the venv python directly, so `uv` is
#  NOT on PATH inside it).
# ---------------------------------------------------------------------------

async def graph_build_task():
    """Rebuild knowledge graphs every 30 minutes."""
    interval = 1800
    eprint("[EmbeddedWatcher] Graph Builder started. Rebuilding every 30 minutes.")
    await asyncio.sleep(60)
    while True:
        eprint(f"\n{'='*50}")
        eprint(f"  GRAPH BUILD — {time.strftime('%Y-%m-%d %H:%M:%S')}")
        eprint(f"{'='*50}")
        for script in ["code_graph.py", "doc_graph.py"]:
            script_path = WATCHER_DIR / script
            if not script_path.exists():
                eprint(f"  [Graph] Script not found: {script_path}")
                continue
            eprint(f"  [Graph] Running {script} --build...")
            try:
                proc = await asyncio.create_subprocess_exec(
                    sys.executable, str(script_path), "--build",
                    cwd=WATCHER_DIR,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
                if stdout:
                    eprint(stdout.decode().rstrip())
                if stderr:
                    eprint(f"  [Graph] stderr: {stderr.decode().rstrip()}")
                if proc.returncode != 0:
                    eprint(f"  [Graph ERROR] {script} exited with code {proc.returncode}")
            except Exception as e:
                eprint(f"  [Graph ERROR] {script} could not run: {e}")
        eprint(f"{'='*50}\n")
        await asyncio.sleep(interval)


# ---------------------------------------------------------------------------
# Watcher main loop (runs inside the background thread's own event loop)
# ---------------------------------------------------------------------------

async def watcher_main(queue: asyncio.Queue, scope: str, run_graph_build: bool):
    if run_graph_build:
        await ensure_fresh_graphs()

    tasks = [
        asyncio.create_task(embedded_worker(queue, scope)),
        asyncio.create_task(reconciler_task()),
        asyncio.create_task(validator_task()),
    ]
    if run_graph_build:
        tasks.append(asyncio.create_task(graph_build_task()))

    try:
        await asyncio.gather(*tasks)
    except asyncio.CancelledError:
        pass


def start_embedded_watcher(scope: str = "code", run_graph_build: bool = True) -> threading.Thread:
    """Launch the embedded watcher in a dedicated background thread."""

    def _thread_target():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        queue: asyncio.Queue = asyncio.Queue()
        observer = Observer()
        handler = AsyncIndexerHandler(loop, queue)

        for repo_name in WATCHED_REPOS:
            repo_path = PROJECT_ROOT / repo_name
            if repo_path.is_dir():
                observer.schedule(handler, str(repo_path), recursive=True)

        for rel_path in EXTRA_COLLECTIONS:
            extra_path = PROJECT_ROOT / rel_path
            if extra_path.is_dir():
                observer.schedule(handler, str(extra_path), recursive=True)

        observer.start()
        eprint(f"[EmbeddedWatcher] Watching {len(WATCHED_REPOS)} repo(s) + extra collections. scope={scope}")

        stop_event = threading.Event()

        def shutdown():
            if stop_event.is_set():
                return
            stop_event.set()
            try:
                observer.stop()
                observer.join(timeout=5)
            except Exception:
                pass
            for task in asyncio.all_tasks(loop):
                task.cancel()
            loop.call_soon_threadsafe(loop.stop)

        atexit.register(shutdown)

        try:
            loop.run_until_complete(watcher_main(queue, scope, run_graph_build))
        finally:
            try:
                loop.close()
            except Exception:
                pass

    t = threading.Thread(target=_thread_target, daemon=False)
    t.start()

    def wait_thread():
        if t.is_alive():
            t.join(timeout=5)

    atexit.register(wait_thread)
    return t
