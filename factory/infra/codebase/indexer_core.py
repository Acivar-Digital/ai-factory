import hashlib
import os

from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PointStruct,
    VectorParams,
)

from config import (
    QDRANT_URL,
    VECTOR_SIZE,
    get_repo_root,
)
from index_state import update_file_state, remove_file_state

# Embeddings are LOCAL ONLY — the user runs their own BGEM3/TEI server
# (BGEM3_URL). Cloud/OpenRouter is removed: there is no fallback. If TEI is
# down the process must FAIL LOUDLY, never silently route to a remote API.
EMBEDDING_MODE = os.getenv("EMBEDDING_MODE", "local").lower()

if EMBEDDING_MODE != "local":
    raise RuntimeError(
        f"EMBEDDING_MODE must be 'local' (user's TEI server). "
        f"Got {EMBEDDING_MODE!r}. Cloud/OpenRouter fallback has been removed — "
        f"fix the deployment or start the local TEI server."
    )

from indexer_local import embed_with_retry, process_file

def _get_client() -> QdrantClient:
    return QdrantClient(url=QDRANT_URL)

def ensure_collection(client: QdrantClient, collection_name: str) -> None:
    """Ensure the Qdrant collection exists."""
    existing = [c.name for c in client.get_collections().collections]
    if collection_name not in existing:
        client.create_collection(
            collection_name=collection_name,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
        print(f"Created collection '{collection_name}'")

async def index_single_file(repo_name: str, collection_name: str, relative_path: str) -> bool:
    """
    Process, embed, and upsert a single file into Qdrant.
    Returns True if successful, False if the file could not be indexed.
    """
    repo_root = get_repo_root(repo_name)
    file_path = repo_root / relative_path

    if not file_path.exists():
        # Edge case: file was deleted right after event
        return False

    # Validate file extension against target collection
    from config import get_allowed_extensions
    if file_path.suffix not in get_allowed_extensions(collection_name):
        print(f"Skipping {relative_path}: extension '{file_path.suffix}' not allowed in collection '{collection_name}'")
        return False

    try:
        content = file_path.read_text(encoding="utf-8")
        current_hash = hashlib.md5(content.encode("utf-8")).hexdigest()
        mtime = file_path.stat().st_mtime
        size = file_path.stat().st_size
    except Exception as e:
        print(f"Error reading {file_path}: {e}")
        return False

    chunks = process_file(file_path, relative_path, current_hash)
    if not chunks:
        # Empty file or unprocessable
        # If it previously existed, we should remove its old vectors
        await remove_single_file(collection_name, relative_path)
        update_file_state(collection_name, relative_path, current_hash, mtime, size)
        return True

    client = _get_client()
    ensure_collection(client, collection_name)

    # Remove any existing points for this file to avoid duplication 
    # if chunk count changed
    client.delete(
        collection_name=collection_name,
        points_selector=Filter(
            must=[FieldCondition(key="file_path", match=MatchValue(value=relative_path))]
        ),
    )

    # Dynamic batching for Cloud/Local consistency
    MAX_BATCH_CHARS = 20000
    MAX_CHUNK_CHARS = 8000
    
    all_vectors = []
    i = 0
    while i < len(chunks):
        batch = []
        current_batch_chars = 0
        
        while i < len(chunks):
            chunk = chunks[i]
            text = chunk["content"][:MAX_CHUNK_CHARS]
            text_len = len(text)
            
            if batch and (current_batch_chars + text_len > MAX_BATCH_CHARS):
                break
            
            batch.append(chunk)
            current_batch_chars += text_len
            i += 1
            
        texts = [c["content"][:MAX_CHUNK_CHARS] for c in batch]
        try:
            batch_vectors = await embed_with_retry(texts)
            all_vectors.extend(batch_vectors)
        except Exception as e:
            print(f"Embedding failed for batch in {relative_path}: {e}")
            all_vectors.extend([[0.0] * VECTOR_SIZE] * len(batch))

    points = []
    for chunk, vector in zip(chunks, all_vectors):
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
                    "file_hash": current_hash, # Track hash in payload for validation
                },
            )
        )
    
    client.upsert(collection_name=collection_name, points=points)
    
    # Update local state ONLY on success
    update_file_state(collection_name, relative_path, current_hash, mtime, size)
    return True


async def remove_single_file(collection_name: str, relative_path: str) -> None:
    """Remove a single file's vectors from Qdrant and update state cache."""
    client = _get_client()
    try:
        client.delete(
            collection_name=collection_name,
            points_selector=Filter(
                must=[FieldCondition(key="file_path", match=MatchValue(value=relative_path))]
            ),
        )
    except Exception as e:
        print(f"Warning: Failed to delete vectors for {relative_path} in {collection_name}: {e}")

    # Remove from local state
    remove_file_state(collection_name, relative_path)
