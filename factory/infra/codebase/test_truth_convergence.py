import os
import sys
import time
import subprocess
import signal
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.models import Filter, FieldCondition, MatchValue

# Assume running from infra/codebase
PROJECT_ROOT = Path(__file__).resolve().parent
TEST_REPO = PROJECT_ROOT / "test_repo_inner"
QDRANT_URL = "http://localhost:6333"
COLLECTION_NAME = "codebase"

client = QdrantClient(url=QDRANT_URL)

def wait_for_daemon(seconds: int = 5):
    """Give the daemon time to debounce and index."""
    time.sleep(seconds)

def verify_file_in_qdrant(relative_path: str, expected: bool, content_match: str = None):
    """Verify that a file exists (or doesn't) in Qdrant, optionally matching payload content."""
    res = client.scroll(
        collection_name=COLLECTION_NAME,
        scroll_filter=Filter(must=[FieldCondition(key="file_path", match=MatchValue(value=relative_path))]),
        limit=10,
        with_payload=True,
        with_vectors=False
    )
    points = res[0]
    exists = len(points) > 0
    
    if expected and not exists:
        print(f"❌ FAILED: Expected {relative_path} in Qdrant, but it's missing.")
        return False
    if not expected and exists:
        print(f"❌ FAILED: Expected {relative_path} to be absent from Qdrant, but it's present.")
        return False
        
    if expected and exists and content_match:
        # Check if content matches in at least one chunk
        matched = any(content_match in pt.payload.get("content", "") for pt in points)
        if not matched:
            print(f"❌ FAILED: File {relative_path} exists, but content '{content_match}' not found.")
            return False
            
    print(f"✅ VERIFIED: {relative_path} {'exists' if expected else 'is absent'} in Qdrant.")
    return True

def start_daemon():
    print("\nStarting daemon in background...")
    env = os.environ.copy()
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "daemon.py")],
        cwd=str(Path(__file__).parent),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        env=env
    )
    time.sleep(3) # Let it initialize
    return proc

def stop_daemon(proc):
    print("\nStopping daemon...")
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

def main():
    print("=== TRUTH CONVERGENCE SYSTEM TEST ===")
    
    # 0. Setup
    if not TEST_REPO.exists():
        TEST_REPO.mkdir(parents=True)
        
    src_dir = TEST_REPO / "src"
    if not src_dir.exists():
        src_dir.mkdir(parents=True)
        
    # Ensure collection exists so scrolling doesn't crash if it's empty
    try:
        if COLLECTION_NAME not in [c.name for c in client.get_collections().collections]:
            from qdrant_client.models import VectorParams, Distance
            client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=VectorParams(size=1024, distance=Distance.COSINE)
            )
    except Exception:
        pass

    # Start daemon
    daemon_proc = start_daemon()

    try:
        # 1. CREATE FILE
        print("\n--- 1. TEST: CREATE FILE ---")
        test_file = src_dir / "truth_test.py"
        test_file.write_text("def initial():\n    return 'initial'\n", encoding="utf-8")
        wait_for_daemon(4) # Watcher debounce is 2s, add buffer
        if not verify_file_in_qdrant("test_repo_inner/src/truth_test.py", True, "initial"):
            sys.exit(1)

        # 2. MODIFY FILE
        print("\n--- 2. TEST: MODIFY FILE ---")
        test_file.write_text("def modified():\n    return 'modified'\n", encoding="utf-8")
        wait_for_daemon(4)
        if not verify_file_in_qdrant("test_repo_inner/src/truth_test.py", True, "modified"):
            sys.exit(1)

        # 3. RENAME FILE
        print("\n--- 3. TEST: RENAME FILE ---")
        renamed_file = src_dir / "truth_renamed.py"
        test_file.rename(renamed_file)
        wait_for_daemon(4)
        if not verify_file_in_qdrant("test_repo_inner/src/truth_test.py", False):
            sys.exit(1)
        if not verify_file_in_qdrant("test_repo_inner/src/truth_renamed.py", True, "modified"):
            sys.exit(1)

        # 4. MOVE FILE
        print("\n--- 4. TEST: MOVE FILE ---")
        other_dir = TEST_REPO / "scripts"
        other_dir.mkdir(exist_ok=True)
        moved_file = other_dir / "truth_renamed.py"
        renamed_file.rename(moved_file)
        wait_for_daemon(4)
        if not verify_file_in_qdrant("test_repo_inner/src/truth_renamed.py", False):
            sys.exit(1)
        if not verify_file_in_qdrant("test_repo_inner/scripts/truth_renamed.py", True, "modified"):
            sys.exit(1)

        # 5. DELETE FILE
        print("\n--- 5. TEST: DELETE FILE ---")
        moved_file.unlink()
        wait_for_daemon(4)
        if not verify_file_in_qdrant("test_repo_inner/scripts/truth_renamed.py", False):
            sys.exit(1)

        # 6. WATCHER FAILURE SIMULATION
        print("\n--- 6. TEST: WATCHER FAILURE SIMULATION ---")
        stop_daemon(daemon_proc)
        
        # Make changes while daemon is dead
        print("Creating missed file while daemon is dead...")
        missed_file = src_dir / "missed_event.py"
        missed_file.write_text("def missing():\n    pass\n", encoding="utf-8")
        
        print("Modifying existing file while daemon is dead...")
        # First create it so it's tracked
        daemon_proc = start_daemon()
        tracked_file = src_dir / "tracked.py"
        tracked_file.write_text("v1", encoding="utf-8")
        wait_for_daemon(4)
        stop_daemon(daemon_proc)
        
        tracked_file.write_text("v2_updated", encoding="utf-8")
        
        # Restart daemon - Reconciler should catch it immediately on startup
        print("Restarting daemon. Reconciler should run immediately and fix state...")
        daemon_proc = start_daemon()
        wait_for_daemon(6) # Let reconciler finish
        
        if not verify_file_in_qdrant("test_repo_inner/src/missed_event.py", True, "missing"):
            sys.exit(1)
        if not verify_file_in_qdrant("test_repo_inner/src/tracked.py", True, "v2_updated"):
            sys.exit(1)
            
        # Clean up
        missed_file.unlink()
        tracked_file.unlink()

        print("\n✅ ALL TESTS PASSED. System is robust and self-healing.")

    finally:
        stop_daemon(daemon_proc)

if __name__ == "__main__":
    main()
