import argparse
import ast
import asyncio
import hashlib
import json
import os
import random
from pathlib import Path
from typing import Any

import httpx
from dotenv import load_dotenv
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    VectorParams,
)

# Load environment variables from root .env
env_path = Path(__file__).parent.parent / ".env"
load_dotenv(env_path)

# Qdrant stored locally inside codebase/
DB_PATH = Path(__file__).parent / "qdrant_db"
COLLECTION_NAME = "codebase_chunks"
VECTOR_SIZE = 1024  # BGEM3 output dimension

# File-level hash cache (so change detection is O(1) per file, not a scroll)
HASH_CACHE_PATH = Path(__file__).parent / ".file_hashes.json"

INCLUDE_DIRS = [
    "src",
    "docs",
    "tests",
    "alt_src",
    "_docs",
    "alt_src",
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
EXCLUDE_DIRS = {
    ".venv",
    "__pycache__",
    ".git",
    "data",
    "logs",
    ".ruff_cache",
    ".mypy_cache",
    "codebase",
}
INCLUDE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    "toml",
    "logs",
    "doc",
    ".bat",
    ".ps1",
    ".sh",
    ".ts",
    ".html",
    ".htm",
    "lock",
    "log",
}

# BGEM3 service (ZeroTier)
BGEM3_URL = os.getenv("BGEM3_URL", "http://localhost:8002/v1/embeddings")
BGEM3_TOKEN = os.getenv("BGEM3_TOKEN", "")


# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


async def embed_with_retry(texts: list[str], max_retries: int = 5, base_delay: float = 2.0) -> list[list[float]]:
    """
    Call BGEM3 service with exponential backoff.
    This ensures the indexer (background) yields to RAG queries (latency-sensitive).
    """
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries):
            try:
                headers = {"Authorization": f"Bearer {BGEM3_TOKEN}"} if BGEM3_TOKEN else {}
                response = await client.post(BGEM3_URL, json=texts, headers=headers)
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict) and "embeddings" in data:
                    return data["embeddings"]
                return data
            except Exception as e:
                if attempt == max_retries - 1:
                    print(f"BGEM3 final retry failed: {e}")
                    raise

                # Exponential backoff: 2s, 4s, 8s, 16s...
                wait = base_delay * (2**attempt)
                # Add jitter to avoid synchronized retries
                wait += random.uniform(0, 1)
                print(f"BGEM3 busy (RAG priority). Retrying in {wait:.1f}s... (Attempt {attempt + 1}/{max_retries})")
                await asyncio.sleep(wait)


# ---------------------------------------------------------------------------
# Hash cache (file-level, persisted to disk)
# ---------------------------------------------------------------------------


def load_hash_cache() -> dict[str, str]:
    if HASH_CACHE_PATH.exists():
        try:
            return json.loads(HASH_CACHE_PATH.read_text())
        except Exception:
            return {}
    return {}


def save_hash_cache(cache: dict[str, str]) -> None:
    HASH_CACHE_PATH.write_text(json.dumps(cache, indent=2))


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_python_file(content: str, file_path: str) -> list[dict[str, Any]]:
    """
    AST-based chunking for Python files.
    Extracts every top-level and nested class/function as its own chunk,
    preserving the exact source lines and correct start_line numbers.
    Falls back to full-file chunk if the file cannot be parsed.
    """
    try:
        tree = ast.parse(content)
    except SyntaxError:
        return [{"content": content, "start_line": 1, "chunk_type": "file_content"}]

    lines = content.splitlines(keepends=True)
    chunks: list[dict[str, Any]] = []
    visited_lines: set = set()

    def extract_node(node: ast.AST) -> None:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            return

        start = node.lineno  # 1-based
        end = node.end_lineno  # 1-based, inclusive

        # Grab decorators too
        if node.decorator_list:
            start = min(d.lineno for d in node.decorator_list)

        block_lines = lines[start - 1 : end]
        block_content = "".join(block_lines).rstrip()

        chunks.append(
            {
                "content": block_content,
                "start_line": start,
                "chunk_type": ("class_def" if isinstance(node, ast.ClassDef) else "function_def"),
            }
        )
        visited_lines.update(range(start, end + 1))

        # Recurse into class bodies so methods are also chunked
        for child in ast.iter_child_nodes(node):
            extract_node(child)

    for node in ast.iter_child_nodes(tree):
        extract_node(node)

    # Any top-level lines not covered by a function/class become an "imports" chunk
    remaining = [line for idx, line in enumerate(lines, start=1) if idx not in visited_lines]
    leftover = "".join(remaining).strip()
    if leftover:
        chunks.insert(0, {"content": leftover, "start_line": 1, "chunk_type": "module_imports"})

    if not chunks:
        chunks.append({"content": content, "start_line": 1, "chunk_type": "file_content"})

    return chunks


def chunk_text_file(content: str) -> list[dict[str, Any]]:
    """Paragraph-based chunking for non-Python files."""
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    return [{"content": p, "start_line": 1, "chunk_type": "text_chunk"} for p in paragraphs]


def process_file(file_path: Path, project_root: Path, file_hash: str) -> list[dict[str, Any]]:
    """Read, chunk, and annotate a single file."""
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []

    if not content.strip():
        return []

    try:
        relative_path = str(file_path.resolve().relative_to(project_root))
    except ValueError:
        relative_path = str(file_path)

    if file_path.suffix == ".py":
        raw_chunks = chunk_python_file(content, relative_path)
    else:
        raw_chunks = chunk_text_file(content)

    for chunk in raw_chunks:
        chunk["file_path"] = relative_path
        chunk["file_name"] = file_path.name
        chunk["file_hash"] = file_hash

    return raw_chunks


# ---------------------------------------------------------------------------
# Main indexer
# ---------------------------------------------------------------------------


async def run_indexer(reset: bool = False) -> None:
    project_root = Path(__file__).parent.parent.resolve()
    DB_PATH.mkdir(parents=True, exist_ok=True)

    client = QdrantClient(path=str(DB_PATH))
    print(f"DEBUG: Qdrant Client path: {DB_PATH}")
    existing = [c.name for c in client.get_collections().collections]

    if reset and COLLECTION_NAME in existing:
        client.delete_collection(COLLECTION_NAME)
        print(f"Reset: deleted collection '{COLLECTION_NAME}'")
        existing = []
        save_hash_cache({})  # clear cache on reset

    if COLLECTION_NAME not in existing:
        client.create_collection(
            collection_name=COLLECTION_NAME,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"Created collection '{COLLECTION_NAME}'")

    # Load file-level hash cache (fast change detection)
    hash_cache = load_hash_cache()

    all_chunks: list[dict[str, Any]] = []
    files_to_delete: list[str] = []  # relative paths of changed files
    new_hashes: dict[str, str] = {}  # updated cache entries

    for include_dir in INCLUDE_DIRS:
        dir_path = project_root / include_dir
        if not dir_path.exists():
            continue

        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix not in INCLUDE_EXTENSIONS:
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8")
                    current_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                    relative_path = str(file_path.resolve().relative_to(project_root))
                except Exception:
                    continue

                cached_hash = hash_cache.get(relative_path)

                if cached_hash == current_hash:
                    # File unchanged — skip
                    continue

                if cached_hash is not None:
                    # File changed — mark old points for deletion
                    print(f"Changed: {relative_path}")
                    files_to_delete.append(relative_path)
                else:
                    print(f"New: {relative_path}")

                chunks = process_file(file_path, project_root, current_hash)
                all_chunks.extend(chunks)
                new_hashes[relative_path] = current_hash

    # Prune stale files (in cache but not on disk)
    missing_files = [path for path in hash_cache if path not in new_hashes and not (project_root / path).exists()]
    if missing_files:
        print(f"Removed: {len(missing_files)} file(s) missing from disk")
        files_to_delete.extend(missing_files)
        # Note: hash_cache will be updated with new_hashes later
        # We need to remove them from hash_cache explicitly if we want to save it
        for path in missing_files:
            if path in hash_cache:
                del hash_cache[path]

    # Delete stale points for changed or missing files
    if files_to_delete:
        client.delete(
            collection_name=COLLECTION_NAME,
            points_selector=Filter(
                must=[
                    FieldCondition(
                        key="file_path",
                        match=MatchAny(any=files_to_delete),
                    )
                ]
            ),
        )
        print(f"Deleted stale vectors for {len(files_to_delete)} file(s)")

    if not all_chunks:
        # Still persist the hash cache if we pruned missing files
        if missing_files:
            save_hash_cache(hash_cache)
        print("No new or changed files to index.")
        return

    print(f"Embedding and indexing {len(all_chunks)} chunks...")

    batch_size = 10
    for i in range(0, len(all_chunks), batch_size):
        batch = all_chunks[i : i + batch_size]
        texts = [c["content"][:8000] for c in batch]  # Truncate to avoid 500 errors or crashing server

        try:
            vectors = await embed_with_retry(texts)
        except Exception as e:
            print(f"Batch {i} failed after retries: {e}. Falling back to zero-vectors.")
            vectors = [[0.0] * VECTOR_SIZE] * len(batch)

        points = []
        for chunk, vector in zip(batch, vectors):
            chunk_id = hashlib.md5(
                f"{chunk['file_path']}:{chunk['start_line']}:{chunk['content'][:64]}".encode()
            ).hexdigest()
            point_id = int(chunk_id[:16], 16) % (2**63)
            points.append(
                PointStruct(
                    id=point_id,
                    vector=vector,
                    payload={
                        "chunk_id": chunk_id,
                        "file_path": chunk["file_path"],
                        "file_name": chunk["file_name"],
                        "start_line": chunk["start_line"],
                        "chunk_type": chunk["chunk_type"],
                        "content": chunk["content"],
                        "file_hash": chunk["file_hash"],
                    },
                )
            )

        client.upsert(collection_name=COLLECTION_NAME, points=points)
        print(f"  {i + len(batch)}/{len(all_chunks)}")

    # Persist updated hash cache
    hash_cache.update(new_hashes)
    save_hash_cache(hash_cache)

    print("Indexing complete.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index codebase into local Qdrant via BGEM3")
    parser.add_argument("--reset", action="store_true", help="Drop collection and re-index from scratch")
    args = parser.parse_args()

    asyncio.run(run_indexer(reset=args.reset))
