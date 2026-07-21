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
from qdrant_client import QdrantClient


from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PointStruct,
    VectorParams,
)

from config import (
    BGEM3_TOKEN,
    BGEM3_URL,
    CODES_DIR,
    EXCLUDE_DIRS,
    EXCLUDE_FILES,
    EXTRA_COLLECTIONS,
    INCLUDE_EXTENSIONS,
    QDRANT_URL,
    STANDARD_DIRS,
    VECTOR_SIZE,
    get_allowed_extensions,
    get_collection_name,
    get_repo_root,
)

# ---------------------------------------------------------------------------
# Embedding
# ---------------------------------------------------------------------------


async def embed_with_retry(texts: list[str], max_retries: int = 5, base_delay: float = 2.0) -> list[list[float]]:
    """Call BGEM3 service with exponential backoff (Local Mac Mini Mode)."""
    is_openai = "v1/embeddings" in BGEM3_URL
    payload = {"input": texts} if is_openai else texts
    async with httpx.AsyncClient(timeout=60.0) as client:
        for attempt in range(max_retries):
            try:
                headers = {"Authorization": f"Bearer {BGEM3_TOKEN}"} if BGEM3_TOKEN else {}
                response = await client.post(
                    BGEM3_URL,
                    json=payload,
                    headers=headers,
                )
                response.raise_for_status()
                data = response.json()
                if isinstance(data, dict):
                    if "data" in data and isinstance(data["data"], list) and len(data["data"]) > 0:
                        return [item["embedding"] for item in data["data"]]
                    elif "embeddings" in data:
                        return data["embeddings"]
                    else:
                        raise ValueError(f"Unexpected response structure from embedding server: {data}")
                return data
            except httpx.HTTPStatusError as e:
                status = e.response.status_code
                if status in (429, 503) and attempt < max_retries - 1:
                    wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"[BGEM3] Service busy (HTTP {status}). Retrying in {wait:.1f}s... (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)
                else:
                    print(f"[BGEM3] HTTP error {status}: {e}")
                    raise
            except httpx.TransportError as e:
                if attempt < max_retries - 1:
                    wait = base_delay * (2 ** attempt) + random.uniform(0, 1)
                    print(f"[BGEM3] Network error ({type(e).__name__}): {e}. Retrying in {wait:.1f}s... (attempt {attempt+1}/{max_retries})")
                    await asyncio.sleep(wait)
                else:
                    print(f"[BGEM3] Final retry failed ({type(e).__name__}): {e}")
                    raise
            except Exception as e:
                print(f"[BGEM3] Unexpected error: {e}")
                raise


# ---------------------------------------------------------------------------
# Hash cache
# ---------------------------------------------------------------------------


def get_hash_cache_path(collection: str) -> Path:
    return CODES_DIR / f".file_hashes_{collection}.json"


def load_hash_cache(cache_path: Path) -> dict[str, str]:
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text())
        except Exception:
            return {}
    return {}


def save_hash_cache(cache: dict[str, str], cache_path: Path) -> None:
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, indent=2))


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------


def chunk_python_file(content: str) -> list[dict[str, Any]]:
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
        start = node.lineno
        end = node.end_lineno
        if node.decorator_list:
            start = min(d.lineno for d in node.decorator_list)

        block_content = "".join(lines[start - 1 : end]).rstrip()
        chunks.append({
            "content": block_content,
            "start_line": start,
            "chunk_type": "class_def" if isinstance(node, ast.ClassDef) else "function_def",
        })
        visited_lines.update(range(start, end + 1))

        for child in ast.iter_child_nodes(node):
            extract_node(child)

    for node in ast.iter_child_nodes(tree):
        extract_node(node)

    remaining = "".join(line for idx, line in enumerate(lines, start=1) if idx not in visited_lines).strip()
    if remaining:
        chunks.insert(0, {"content": remaining, "start_line": 1, "chunk_type": "module_imports"})
    if not chunks:
        chunks.append({"content": content, "start_line": 1, "chunk_type": "file_content"})
    return chunks


def chunk_text_file(content: str) -> list[dict[str, Any]]:
    paragraphs = [p.strip() for p in content.split("\n\n") if p.strip()]
    return [{"content": p, "start_line": 1, "chunk_type": "text_chunk"} for p in paragraphs]


def process_file(file_path: Path, relative_path: str, file_hash: str) -> list[dict[str, Any]]:
    try:
        content = file_path.read_text(encoding="utf-8")
    except Exception:
        return []
    if not content.strip():
        return []

    raw_chunks = chunk_python_file(content) if file_path.suffix == ".py" else chunk_text_file(content)

    for chunk in raw_chunks:
        chunk["file_path"] = relative_path
        chunk["file_name"] = file_path.name
        chunk["file_hash"] = file_hash
    return raw_chunks


# ---------------------------------------------------------------------------
# Include-dir resolution for extra collections
# ---------------------------------------------------------------------------


def _get_include_dirs(repo_name: str) -> list[str]:
    """Return the include dirs for a given repo/collection name.

    Extra collections (e.g. "infra/codebase") walk "." (the dir itself).
    Normal repos walk STANDARD_DIRS (src, docs, tests, ...).
    """
    if repo_name in EXTRA_COLLECTIONS:
        return ["."]
    return STANDARD_DIRS


# ---------------------------------------------------------------------------
# Main indexer
# ---------------------------------------------------------------------------


async def run_indexer(
    repo_name: str,
    include_dirs: list[str] | None = None,
    collection_name: str | None = None,
    reset: bool = False,
    allowed_extensions: set[str] | None = None,
) -> None:
    if include_dirs is None:
        include_dirs = _get_include_dirs(repo_name)
    if collection_name is None:
        collection_name = repo_name.split("/")[-1]
    if allowed_extensions is None:
        allowed_extensions = INCLUDE_EXTENSIONS

    hash_cache_path = get_hash_cache_path(collection_name)

    print(f"Connecting to Qdrant at {QDRANT_URL}...")
    client = QdrantClient(url=QDRANT_URL, check_compatibility=False)
    print(f"Connected to Qdrant at {QDRANT_URL}")
    print(f"Repo: {repo_name} -> Collection: {collection_name}")

    print("Fetching collections...")
    existing = [c.name for c in client.get_collections().collections]
    print(f"Collections: {existing}")

    if reset and collection_name in existing:
        client.delete_collection(collection_name)
        print(f"Reset: deleted collection '{collection_name}'")
        existing = []
        save_hash_cache({}, hash_cache_path)

    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"Created collection '{collection_name}'")

    hash_cache = load_hash_cache(hash_cache_path)
    all_chunks: list[dict[str, Any]] = []
    files_to_delete: list[str] = []
    new_hashes: dict[str, str] = {}
    scanned_paths: set[str] = set()

    repo_root = get_repo_root(repo_name)

    for include_dir in include_dirs:
        dir_path = repo_root / include_dir
        if not dir_path.exists():
            continue

        for root, dirs, files in os.walk(dir_path):
            dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
            for file in files:
                file_path = Path(root) / file
                if file_path.suffix not in allowed_extensions:
                    continue
                if file_path.name in EXCLUDE_FILES:
                    continue
                if file_path.suffix == ".json" and CODES_DIR in file_path.parents:
                    continue

                try:
                    relative_path = str(file_path.resolve().relative_to(repo_root))
                    content = file_path.read_text(encoding="utf-8")
                    current_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
                except Exception:
                    continue

                scanned_paths.add(relative_path)

                if hash_cache.get(relative_path) == current_hash:
                    continue

                if relative_path in hash_cache:
                    print(f"Changed: {relative_path}")
                    files_to_delete.append(relative_path)
                else:
                    print(f"New: {relative_path}")

                chunks = process_file(file_path, relative_path, current_hash)
                all_chunks.extend(chunks)
                new_hashes[relative_path] = current_hash

    # Prune hash cache entries for files that no longer match include/exclude rules
    pruned_paths = [p for p in hash_cache if p not in scanned_paths]
    if pruned_paths:
        for p in pruned_paths:
            print(f"Excluded: {p}")
        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="file_path", match=MatchAny(any=pruned_paths))]
            ),
        )
        print(f"Deleted vectors for {len(pruned_paths)} excluded file(s)")
        for p in pruned_paths:
            hash_cache.pop(p, None)

    if files_to_delete:
        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="file_path", match=MatchAny(any=files_to_delete))]
            ),
        )
        print(f"Deleted stale vectors for {len(files_to_delete)} file(s)")

    if not all_chunks:
        if not pruned_paths:
            print("No new or changed files to index.")
        hash_cache.update(new_hashes)
        save_hash_cache(hash_cache, hash_cache_path)
        return

    print(f"Embedding and indexing {len(all_chunks)} chunks...")
    
    # Dynamic batching based on total character limit (20K window)
    MAX_BATCH_CHARS = 20000
    MAX_CHUNK_CHARS = 8000
    
    i = 0
    while i < len(all_chunks):
        batch = []
        current_batch_chars = 0
        
        # Pack as many chunks as possible into this batch
        while i < len(all_chunks):
            chunk = all_chunks[i]
            text = chunk["content"][:MAX_CHUNK_CHARS]
            text_len = len(text)
            
            # If adding this chunk exceeds the batch limit, stop here
            if batch and (current_batch_chars + text_len > MAX_BATCH_CHARS):
                break
                
            batch.append(chunk)
            current_batch_chars += text_len
            i += 1

        texts = [c["content"][:MAX_CHUNK_CHARS] for c in batch]
        try:
            vectors = await embed_with_retry(texts, max_retries=10, base_delay=1.0)
        except Exception as e:
            print(f"Batch at index {i-len(batch)} failed: {e}.")
            vectors = [[0.0] * VECTOR_SIZE] * len(batch)
        
        await asyncio.sleep(0.3)

        points = []
        for chunk, vector in zip(batch, vectors):
            chunk_id_str = f"{chunk['file_path']}:{chunk['start_line']}:{chunk['content'][:64]}"
            chunk_id = int(hashlib.md5(chunk_id_str.encode()).hexdigest()[:16], 16) % (2**63)
            points.append(
                PointStruct(
                    id=chunk_id,
                    vector=vector,
                    payload={
                        "file_path": chunk["file_path"],
                        "file_name": chunk["file_name"],
                        "start_line": chunk["start_line"],
                        "chunk_type": chunk["chunk_type"],
                        "content": chunk["content"],
                    },
                )
            )
        client.upsert(collection_name=collection_name, points=points)
        print(f"  {i}/{len(all_chunks)} (Batch size: {len(batch)}, chars: {current_batch_chars})")

    hash_cache.update(new_hashes)
    save_hash_cache(hash_cache, hash_cache_path)
    print("Indexing complete.")


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Index codebase into local Qdrant via BGEM3 (LOCAL MODE)")
    parser.add_argument("--repo", default="baziforecaster", help="Name of the repo folder or extra collection path to index")
    parser.add_argument("--collection", default=None, help="Name of the Qdrant collection (defaults to repo name)")
    args = parser.parse_args()

    collection = args.collection or get_collection_name(args.repo)
    include_dirs = _get_include_dirs(args.repo)
    allowed_exts = get_allowed_extensions(collection)

    asyncio.run(run_indexer(
        repo_name=args.repo,
        include_dirs=include_dirs,
        collection_name=collection,
        reset=False,
        allowed_extensions=allowed_exts,
    ))
